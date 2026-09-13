"""
CivicPulse — Evidence Storage Helper
======================================
Abstracts where uploaded evidence files are physically stored:

  Production  : Supabase Storage (private bucket, signed-URL access)
  Local dev   : Local filesystem under UPLOAD_DIR/evidence/

Policy
------
* In production (SUPABASE_URL set), never falls back to local disk.  A
  missing Supabase configuration raises a clear error rather than silently
  writing to an ephemeral filesystem.
* Stable *object keys* (not signed URLs) are stored in PostgreSQL.  Signed
  URLs are generated on demand at read time and are valid for one hour.
* File validation and authorization remain in the route layer; this module
  only handles I/O.
* Partial-failure cleanup is supported via ``delete_evidence()``.

Environment variables consumed (all read at import time):
  SUPABASE_URL             — e.g. https://xyzxyz.supabase.co
  SUPABASE_SERVICE_KEY     — service-role secret (NOT the anon key)
  SUPABASE_STORAGE_BUCKET  — bucket name (default: "evidence")
  UPLOAD_DIR               — local upload root (default: "uploads")
  RENDER / PRODUCTION      — set to any value to signal prod environment
"""

from __future__ import annotations

import logging
import os
import uuid
import io
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

_SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "").rstrip("/")
_SUPABASE_SERVICE_KEY: str = os.environ.get("SUPABASE_SERVICE_KEY", "")
_BUCKET_NAME: str = os.environ.get("SUPABASE_STORAGE_BUCKET", "evidence")
_LOCAL_UPLOAD_DIR: str = os.environ.get("UPLOAD_DIR", "uploads")

# ============================================================
# HELPERS
# ============================================================

def is_storage_configured() -> bool:
    """Return True when Supabase Storage credentials are present."""
    return bool(_SUPABASE_URL and _SUPABASE_SERVICE_KEY)


def _is_production() -> bool:
    """
    Return True when the process is running in a production-like environment.
    Render sets RENDER=true; any deployment can set PRODUCTION=true.
    PRODUCTION="false" / "0" / "no" are correctly treated as non-production.
    """
    prod_val = os.environ.get("PRODUCTION", "false").lower()
    if prod_val in ("true", "1", "yes", "y", "t"):
        return True
    if os.environ.get("RENDER"):
        return True
    return False


def _get_supabase_client():
    """
    Return an initialised supabase-py client using the service-role key.
    The service-role key bypasses RLS — it must NEVER be exposed to the
    frontend or included in any response.
    """
    try:
        from supabase import create_client  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "supabase-py is not installed. "
            "Run: pip install 'supabase>=2.0,<3.0'"
        ) from exc
    return create_client(_SUPABASE_URL, _SUPABASE_SERVICE_KEY)


# ============================================================
# OBJECT KEY GENERATION
# ============================================================

# Map MIME type → file extension
_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def make_object_key(
    complaint_id: int,
    original_filename: str,
    content_type: str = "image/jpeg",
) -> str:
    """
    Generate a unique, safe object key for Supabase Storage.

    Format:  evidence/{complaint_id}/{uuid}.{ext}

    The key is URL-safe (no special chars), globally unique (UUID4), and
    contains enough context to identify the complaint without exposing the
    original filename.
    """
    ext = _MIME_TO_EXT.get(
        (content_type or "").split(";")[0].strip().lower(),
        Path(original_filename).suffix or ".bin",
    )
    uid = uuid.uuid4().hex
    return f"evidence/{complaint_id}/{uid}{ext}"


# Alias for backward compatibility / migration script
generate_evidence_key = make_object_key


# ============================================================
# UPLOAD AND VALIDATION
# ============================================================

async def validate_evidence(file: UploadFile) -> bytes:
    MAX_SIZE = 10 * 1024 * 1024
    ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Only JPEG, PNG, GIF, and WEBP are allowed.")

    file_bytes = bytearray()
    while chunk := await file.read(65536):
        file_bytes.extend(chunk)
        if len(file_bytes) > MAX_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file.")

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
        
        if hasattr(Image, "MAX_IMAGE_PIXELS") and Image.MAX_IMAGE_PIXELS:
            pixels = img.size[0] * img.size[1]
            if pixels > Image.MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=400, detail="Image exceeds maximum pixel limit.")
    except ImportError:
        logger.warning("Pillow not installed, skipping deep image validation.")
    except Exception:
        raise HTTPException(status_code=400, detail="Corrupted or invalid image file.")

    return bytes(file_bytes)

def upload_evidence(
    file_bytes: bytes,
    object_key: str,
    content_type: str = "image/jpeg",
) -> str:
    """
    Upload *file_bytes* to Supabase Storage at *object_key*.

    Returns the *object_key* (the stable value to store in PostgreSQL).

    Raises ``RuntimeError`` on failure so the route can perform compensating
    cleanup and return a proper HTTP error to the client.

    In local development (storage not configured), writes to the local
    filesystem under UPLOAD_DIR/evidence/ and returns a local-style path
    that the ``/uploads`` static route can serve.

    Does NOT fall back to local disk when RENDER or PRODUCTION env var is
    set — fails clearly instead.
    """
    if is_storage_configured():
        client = _get_supabase_client()
        try:
            client.storage.from_(_BUCKET_NAME).upload(
                path=object_key,
                file=file_bytes,
                file_options={
                    "content-type": content_type,
                    "upsert": "false",
                },
            )
            logger.debug("Uploaded evidence to Supabase: %s", object_key)
            return object_key

        except Exception as exc:
            raise RuntimeError(
                f"Supabase Storage upload failed for '{object_key}': {exc}"
            ) from exc

    # ── Local filesystem fallback (development only) ──────────────────────
    if _is_production():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY are not configured but "
            "the server appears to be running in production mode.  "
            "Set these environment variables to enable evidence uploads."
        )

    upload_dir = Path(_LOCAL_UPLOAD_DIR) / "evidence"
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Use just the final filename segment from the object key
    local_filename = Path(object_key).name
    local_path = upload_dir / local_filename
    local_path.write_bytes(file_bytes)

    # Return a local-style path (relative to upload root) for DB storage.
    # The /uploads static mount in main.py will serve it.
    local_key = str(Path("uploads") / "evidence" / local_filename).replace(
        "\\", "/"
    )
    logger.debug("Saved evidence locally: %s", local_path)
    return local_key


# ============================================================
# SIGNED URL / ACCESS URL
# ============================================================

def get_evidence_url(object_key: str, expires_in: int = 3600) -> str:
    """
    Return a URL that can be used to display or download the evidence file.

    * Supabase  : a signed URL valid for *expires_in* seconds (default 1 h).
    * Local dev : the relative path (e.g. ``uploads/evidence/abc.jpg``)
                  that the frontend will prepend with the API base URL.

    Returns an empty string on any failure (non-fatal; caller decides how
    to handle missing evidence URLs).
    """
    if not object_key:
        return ""

    if is_storage_configured():
        try:
            client = _get_supabase_client()
            result = client.storage.from_(_BUCKET_NAME).create_signed_url(
                path=object_key,
                expires_in=expires_in,
            )
            # supabase-py 2.x uses "signedURL"; older versions "signedUrl"
            return (
                result.get("signedURL")
                or result.get("signedUrl")
                or ""
            )
        except Exception as exc:
            logger.warning(
                "Failed to generate signed URL for '%s': %s", object_key, exc
            )
            return ""

    # Local dev: strip any leading slashes; frontend prepends API_URL
    return object_key.lstrip("/")


# ============================================================
# COMPENSATING CLEANUP (DELETE)
# ============================================================

def delete_evidence(object_key: str) -> bool:
    """
    Delete an uploaded evidence file.  Called as compensating cleanup when
    a subsequent database write fails after a successful upload.

    Returns True on success, False on failure (non-fatal — log and move on).
    """
    if not object_key:
        return True

    if is_storage_configured():
        try:
            client = _get_supabase_client()
            client.storage.from_(_BUCKET_NAME).remove([object_key])
            logger.debug("Deleted evidence from Supabase: %s", object_key)
            return True
        except Exception as exc:
            logger.warning(
                "Failed to delete evidence '%s' from Supabase: %s",
                object_key, exc,
            )
            return False

    # Local fallback: try to remove the file
    try:
        # object_key stored as uploads/evidence/filename for local dev
        local_path = Path(object_key)
        if not local_path.is_absolute():
            local_path = Path(_LOCAL_UPLOAD_DIR) / "evidence" / local_path.name
        if local_path.exists():
            local_path.unlink()
        return True
    except Exception as exc:
        logger.warning(
            "Failed to delete local evidence '%s': %s", object_key, exc
        )
        return False


# ============================================================
# RECOVERY TASK RECORDING (Uncertain Commit Reconciliation)
# ============================================================

_RECOVERY_TASKS_LEDGER: list[dict] = []


def record_recovery_task(task_type: str, details: dict) -> dict:
    """
    Record a recovery task when a database commit outcome is uncertain
    (e.g., connection loss during commit) and the image was retained.

    Writes to structured logger, appends to the in-memory ledger, and persists
    to recovery_tasks.jsonl for operator or background reconciliation.
    """
    import json
    import time

    task_entry = {
        "id": str(uuid.uuid4()),
        "task_type": task_type,
        "timestamp": time.time(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "details": details,
        "status": "pending_reconciliation",
    }
    _RECOVERY_TASKS_LEDGER.append(task_entry)

    logger.critical(
        "RECOVERY TASK RECORDED [%s]: %s (details: %s)",
        task_entry["id"],
        task_type,
        details,
    )

    try:
        log_file = Path(_LOCAL_UPLOAD_DIR) / "recovery_tasks.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(task_entry) + "\n")
    except Exception as write_err:
        logger.error("Failed to append recovery task to disk: %s", write_err)

    return task_entry


def get_recovery_tasks() -> list[dict]:
    """Return in-memory recovery tasks (useful for inspection and testing)."""
    return list(_RECOVERY_TASKS_LEDGER)

