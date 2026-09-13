"""
CivicPulse — Embedding Service
================================
Generates and stores Gemini text embeddings for complaints.
Used by the vector-based duplicate detection pipeline.

Config env vars:
    GEMINI_API_KEY          — required (same key as classifier)
    GEMINI_EMBEDDING_MODEL  — optional, default: text-embedding-004
    EMBEDDING_VERSION       — optional label for cache invalidation
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from backend.app.services import db_compat

logger = logging.getLogger(__name__)

EMBEDDING_MODEL: str = os.environ.get("GEMINI_EMBEDDING_MODEL", "text-embedding-004")
EMBEDDING_VERSION: str = os.environ.get("EMBEDDING_VERSION", "v1")
EMBEDDING_DIM = 768  # text-embedding-004 default output dimension


def build_complaint_text(category: str, description: str) -> str:
    """
    Build a canonical text for embedding from complaint fields.
    Deterministic — same inputs always produce the same string.
    """
    category = (category or "").strip()
    description = (description or "").strip()
    return f"Category: {category}\nDescription: {description}"


def generate_embedding(text: str) -> Optional[list[float]]:
    """
    Call the Gemini embedding API and return a float list.
    Returns None on any failure so the caller can gracefully skip.
    """
    try:
        from backend.app.ai.config import get_gemini_api_key
        from google import genai

        api_key = get_gemini_api_key()
        if not api_key:
            logger.warning("Embedding skipped: GEMINI_API_KEY not set.")
            return None

        client = genai.Client(api_key=api_key)
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
        )
        
        values = response.embeddings[0].values if getattr(response, "embeddings", None) else None
        
        if not values or len(values) != EMBEDDING_DIM:
            logger.warning("Embedding API returned empty or invalid dimension vector.")
            return None
        return list(values)

    except ImportError:
        logger.warning("google-genai SDK not installed — embedding skipped.")
        return None
    except Exception as exc:
        logger.warning("Embedding generation failed: %s", exc)
        return None


def store_complaint_embedding(
    db,
    complaint_id: int,
    embedding: list[float],
) -> bool:
    """
    Persist the embedding vector into the complaints table.
    Works with both SQLite (JSON blob) and PostgreSQL (pgvector).
    Returns True on success.
    """
    import json
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    try:
        # Use db_compat for reliable SQLite vs PostgreSQL detection
        if db_compat.is_sqlite(db):
            # SQLite: store embedding as JSON text in embedding_json column
            cursor = db.cursor()

            # Ensure all embedding columns exist (idempotent)
            cursor.execute("PRAGMA table_info(complaints)")
            cols = [r[1] for r in cursor.fetchall()]
            for col, col_type in (
                ("embedding_json", "TEXT"),
                ("embedding_model", "TEXT"),
                ("embedding_created_at", "TEXT"),
                ("embedding_version", "TEXT"),
            ):
                if col not in cols:
                    cursor.execute(
                        f"ALTER TABLE complaints ADD COLUMN {col} {col_type}"
                    )

            cursor.execute(
                """
                UPDATE complaints
                SET embedding_json = ?,
                    embedding_model = ?,
                    embedding_created_at = ?,
                    embedding_version = ?
                WHERE id = ?
                """,
                (
                    json.dumps(embedding),
                    EMBEDDING_MODEL,
                    now,
                    EMBEDDING_VERSION,
                    complaint_id,
                ),
            )
            db.commit()

        else:
            # PostgreSQL with pgvector: use %s placeholders directly.
            # The ::vector cast must stay as a SQL literal — db_compat.execute
            # would double-convert it, so we call cursor.execute directly.
            vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
            cursor = db.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE complaints
                    SET embedding = %s::vector,
                        embedding_model = %s,
                        embedding_created_at = %s,
                        embedding_version = %s
                    WHERE id = %s
                    """,
                    (vec_str, EMBEDDING_MODEL, now, EMBEDDING_VERSION, complaint_id),
                )
                db.commit()
            except Exception as pg_err:
                db.rollback()
                logger.info("pgvector not available or error, falling back to embedding_json: %s", pg_err)
                cursor = db.cursor()
                cursor.execute(
                    """
                    UPDATE complaints
                    SET embedding_json = %s,
                        embedding_model = %s,
                        embedding_created_at = %s,
                        embedding_version = %s
                    WHERE id = %s
                    """,
                    (json.dumps(embedding), EMBEDDING_MODEL, now, EMBEDDING_VERSION, complaint_id),
                )
                db.commit()

        return True

    except Exception as exc:
        logger.warning("Failed to store embedding for complaint %s: %s", complaint_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return False


def embed_complaint(db, complaint_id: int, category: str, description: str) -> bool:
    """
    High-level helper: generate + store an embedding for a complaint.
    Returns True on success, False on any failure.
    Failure does NOT prevent complaint creation.
    """
    text = build_complaint_text(category, description)
    embedding = generate_embedding(text)
    if embedding is None:
        return False
    return store_complaint_embedding(db, complaint_id, embedding)
