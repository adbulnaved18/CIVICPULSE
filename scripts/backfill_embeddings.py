#!/usr/bin/env python3
"""
CivicPulse — Embedding Backfill Script
========================================
Generates Gemini embeddings for all existing complaints that
don't have one yet.  Safe to run multiple times (idempotent).

Usage:
    python scripts/backfill_embeddings.py [--batch-size 50] [--delay 1.0]
"""

import argparse
import sys
import time
from pathlib import Path

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass

from backend.app.services.database import get_db
from backend.app.services.embedding_service import embed_complaint


def main():
    parser = argparse.ArgumentParser(description="Backfill complaint embeddings")
    parser.add_argument("--batch-size", type=int, default=50, help="Complaints per batch")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between batches (rate limiting)")
    args = parser.parse_args()

    db = get_db()
    cursor = db.cursor()

    # Find complaints without embeddings
    # For SQLite we use embedding_json; for Postgres we'd use embedding IS NULL
    try:
        cursor.execute("PRAGMA table_info(complaints)")
        cols = [r[1] for r in cursor.fetchall()]
        if "embedding_json" in cols:
            cursor.execute(
                "SELECT id, category, description FROM complaints WHERE embedding_json IS NULL ORDER BY id DESC"
            )
        else:
            # embedding_json column not added yet — add it
            cursor.execute(
                "SELECT id, category, description FROM complaints ORDER BY id DESC"
            )
    except Exception as e:
        print(f"ERROR reading complaints: {e}")
        db.close()
        sys.exit(1)

    rows = cursor.fetchall()
    total = len(rows)
    print(f"Complaints needing embeddings: {total}")

    if total == 0:
        print("Nothing to do.")
        db.close()
        return

    success = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        cid, category, description = row[0], row[1], row[2]
        ok = embed_complaint(db, cid, category or "", description or "")
        if ok:
            success += 1
        else:
            failed += 1

        if i % args.batch_size == 0 or i == total:
            print(f"  Progress: {i}/{total} — success={success}, failed={failed}")
            if i < total:
                time.sleep(args.delay)

    db.close()
    print(f"\nBackfill complete: {success} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()
