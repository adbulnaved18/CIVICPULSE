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
            content=text,
        )
        values = response.embedding.values
        if not values:
            logger.warning("Embedding API returned empty vector.")
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
        cursor = db.cursor()

        # Detect database type
        cursor.execute("SELECT 1")
        db_type = type(db).__module__

        if "sqlite3" in db_type or hasattr(db, "row_factory"):
            # SQLite: store as JSON text in a text column (migration step)
            # First ensure the column exists
            cursor.execute("PRAGMA table_info(complaints)")
            cols = [r[1] for r in cursor.fetchall()]
            if "embedding_json" not in cols:
                cursor.execute(
                    "ALTER TABLE complaints ADD COLUMN embedding_json TEXT"
                )
            if "embedding_model" not in cols:
                cursor.execute(
                    "ALTER TABLE complaints ADD COLUMN embedding_model TEXT"
                )
            if "embedding_created_at" not in cols:
                cursor.execute(
                    "ALTER TABLE complaints ADD COLUMN embedding_created_at TEXT"
                )
            if "embedding_version" not in cols:
                cursor.execute(
                    "ALTER TABLE complaints ADD COLUMN embedding_version TEXT"
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
            # PostgreSQL with pgvector
            cursor.execute(
                """
                UPDATE complaints
                SET embedding = %s::vector,
                    embedding_model = %s,
                    embedding_created_at = %s,
                    embedding_version = %s
                WHERE id = %s
                """,
                (embedding, EMBEDDING_MODEL, now, EMBEDDING_VERSION, complaint_id),
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
