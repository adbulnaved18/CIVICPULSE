# ============================================================
# CivicPulse — AI Router
# ============================================================
#
# Endpoints:
#   GET  /ai/health          — AI service availability check
#   POST /ai/transcribe      — speech-to-text (audio → transcript)
#   POST /ai/analyze-report  — classify complaint (text + image)
#
# All endpoints require authentication (httpOnly cookie).
# The GEMINI_API_KEY is never returned in any response.
# ============================================================

from __future__ import annotations

import hashlib
import io
import logging
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from backend.app.ai.config import (
    AI_MAX_AUDIO_BYTES,
    AI_MAX_IMAGE_BYTES,
    ALLOWED_AUDIO_MIME_TYPES,
    ALLOWED_IMAGE_MIME_TYPES,
    is_ai_available,
)
from backend.app.ai.gemini_service import (
    transcribe_audio,
    analyze_report,
    is_provider_sdk_available,
)
from backend.app.ai.schemas import AIHealthResponse, AnalyzeResponse, TranscribeResponse
from backend.app.ai.prompts import PROMPT_VERSION
from backend.app.auth.dependencies import get_current_user
from backend.app.services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)


# ============================================================
# HELPERS
# ============================================================

def _validate_audio(content_type: str, size: int) -> None:
    """Raise 400 if the audio file is unsupported or too large."""
    # Normalise content-type (strip parameters like ;codecs=...)
    base_type = content_type.split(";")[0].strip().lower()
    full_type = content_type.strip().lower()

    if base_type not in ALLOWED_AUDIO_MIME_TYPES and full_type not in ALLOWED_AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio type: {base_type}. "
                   "Accepted: webm, wav, mp3, mp4, m4a, ogg, flac.",
        )

    if size > AI_MAX_AUDIO_BYTES:
        mb = AI_MAX_AUDIO_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file exceeds the {mb} MB limit.",
        )


def _validate_image(content_type: str, size: int) -> None:
    """Raise 400/413 if the image file is unsupported or too large."""
    base_type = content_type.split(";")[0].strip().lower()

    if base_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type: {base_type}. "
                   "Accepted: jpeg, png, gif, webp.",
        )

    if size > AI_MAX_IMAGE_BYTES:
        mb = AI_MAX_IMAGE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {mb} MB limit.",
        )


def _validate_and_resize_image(raw_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    """
    Decode the image with Pillow to confirm it is a real image,
    strip metadata, and downscale if very large.

    Returns (processed_bytes, mime_type).
    Falls back to original bytes if Pillow is not installed.
    """
    try:
        from PIL import Image, UnidentifiedImageError  # type: ignore

        try:
            img = Image.open(io.BytesIO(raw_bytes))
        except UnidentifiedImageError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is not a valid image.",
            )

        # Strip EXIF / metadata by re-saving without it.
        img = img.convert("RGB")

        # Downscale to 1024×1024 max to reduce token usage.
        img.thumbnail((1024, 1024))

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue(), "image/jpeg"

    except HTTPException:
        raise

    except ImportError:
        # Pillow not installed — pass bytes through without processing.
        logger.warning("Pillow not installed; skipping image validation.")
        return raw_bytes, mime_type

    except Exception:
        logger.warning("Image processing failed; using original bytes.")
        return raw_bytes, mime_type


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ============================================================
# GET /ai/health
# ============================================================

@router.get(
    "/health",
    response_model=AIHealthResponse,
    summary="AI service health check",
)
def ai_health():
    """
    Returns whether the AI service is configured and available.
    Does NOT expose the API key or any secret.
    """
    key_configured = is_ai_available()
    sdk_available = is_provider_sdk_available()
    available = key_configured and sdk_available

    if not key_configured:
        message = "AI service is not configured. Set GEMINI_API_KEY on the backend server."
    elif not sdk_available:
        message = (
            "AI dependency is missing. Run: pip install -r backend/requirements.txt"
        )
    else:
        message = "AI service is configured."

    return AIHealthResponse(
        ai_available=available,
        message=message,
    )


# ============================================================
# POST /ai/transcribe
# ============================================================

@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    summary="Transcribe audio to text (English / Hindi)",
)
async def transcribe_endpoint(
    audio: UploadFile = File(..., description="Audio file (webm/wav/mp3/m4a)"),
    language_hint: Optional[str] = Form(
        default=None,
        description="Optional language hint: 'en' or 'hi'",
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Convert a short audio clip to text.

    - Requires authentication.
    - Accepts webm, wav, mp3, m4a, ogg, flac.
    - Maximum file size: 10 MB / 90 seconds.
    - Raw audio is NOT stored permanently.
    """
    if not is_ai_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured on this server.",
        )

    # Read and validate.
    audio_bytes = await audio.read()
    content_type = audio.content_type or "audio/webm"
    _validate_audio(content_type, len(audio_bytes))

    try:
        result = await transcribe_audio(
            file_bytes=audio_bytes,
            filename=audio.filename or "recording.webm",
            language_hint=language_hint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    return TranscribeResponse(**result)


# ============================================================
# POST /ai/analyze-report
# ============================================================

@router.post(
    "/analyze-report",
    response_model=AnalyzeResponse,
    summary="Classify a civic complaint into one of 12 categories",
)
async def analyze_report_endpoint(
    description: Optional[str] = Form(
        default=None,
        description="Complaint description text (optional if image provided)",
    ),
    image: Optional[UploadFile] = File(
        default=None,
        description="Optional photo evidence",
    ),
    selected_category: Optional[str] = Form(
        default=None,
        description="Category the user has manually selected (hint only)",
    ),
    language: Optional[str] = Form(
        default=None,
        description="Language hint: 'en' or 'hi'",
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Analyze a complaint description and/or image and return:
    - suggested category (one of the 12 CivicPulse categories)
    - confidence score
    - whether human review is needed
    - detected language
    - brief reason
    - consistency check between text and image

    The returned analysis_id must be submitted with the final complaint
    for audit purposes.
    """
    if not is_ai_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured on this server.",
        )

    if not description and not image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of description or image is required.",
        )

    # --------------------------------------------------------
    # Process image
    # --------------------------------------------------------
    image_bytes: Optional[bytes] = None
    image_mime: Optional[str] = None
    image_sha: Optional[str] = None

    if image and image.filename:
        raw_image = await image.read()
        content_type = image.content_type or "image/jpeg"
        _validate_image(content_type, len(raw_image))

        image_bytes, image_mime = _validate_and_resize_image(raw_image, content_type)
        image_sha = _sha256(raw_image)  # hash of original for audit

    # --------------------------------------------------------
    # Compute text hash for audit
    # --------------------------------------------------------
    text_sha: Optional[str] = None
    if description and description.strip():
        text_sha = _sha256(description.strip().encode("utf-8"))

    if not text_sha and not image_sha:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not process the provided inputs.",
        )

    # --------------------------------------------------------
    # Call the AI
    # --------------------------------------------------------
    try:
        analysis = await analyze_report(
            description=description,
            image_bytes=image_bytes,
            image_mime=image_mime,
            selected_category=selected_category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    # --------------------------------------------------------
    # Persist the analysis record for audit / hash verification
    # --------------------------------------------------------
    analysis_id = str(uuid.uuid4())

    db = get_db()
    try:
        db.execute(
            """
            INSERT INTO report_ai_analyses (
                id,
                user_id,
                text_sha256,
                image_sha256,
                suggested_category,
                confidence,
                needs_review,
                detected_language,
                short_reason,
                text_image_consistent,
                provider,
                model,
                prompt_version,
                expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      datetime('now', '+1 hour'))
            """,
            (
                analysis_id,
                current_user["id"],
                text_sha or "",
                image_sha,
                analysis.suggested_category,
                analysis.confidence,
                int(analysis.needs_review),
                analysis.detected_language,
                analysis.short_reason,
                (
                    None
                    if analysis.text_image_consistent is None
                    else int(analysis.text_image_consistent)
                ),
                "gemini",
                "multimodal",
                PROMPT_VERSION,
            ),
        )
        db.commit()
    except Exception as exc:
        logger.error("Failed to save analysis record: %s", type(exc).__name__)
        # Non-fatal — still return the result to the user.
        db.rollback()
    finally:
        db.close()

    return AnalyzeResponse(
        analysis_id=analysis_id,
        suggested_category=analysis.suggested_category,
        confidence=analysis.confidence,
        needs_review=analysis.needs_review,
        detected_language=analysis.detected_language,
        short_reason=analysis.short_reason,
        text_image_consistent=analysis.text_image_consistent,
        alternative_category=analysis.alternative_category,
    )
