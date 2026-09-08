#!/usr/bin/env python3
"""
CivicPulse — SQLite to PostgreSQL migration script.

Usage:
    python scripts/migrate_sqlite_to_postgres.py

Requires DATABASE_URL to be set in your environment or .env file:
    DATABASE_URL=postgresql://user:password@localhost:5432/civicpulse

The script is idempotent: existing rows (matched by PK) are skipped.
"""

import os
import sys
import sqlite3
from pathlib import Path

# --------------------------------------------------------
# Load .env if present
# --------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    print("ERROR: DATABASE_URL must start with 'postgresql://'")
    print("  Set: DATABASE_URL=postgresql://user:password@localhost:5432/civicpulse")
    sys.exit(1)

try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("ERROR: sqlalchemy not installed. Run: pip install sqlalchemy psycopg2-binary")
    sys.exit(1)

# --------------------------------------------------------
# Resolve SQLite path
# --------------------------------------------------------
project_root = Path(__file__).resolve().parents[1]
sqlite_path = project_root / "database" / "civicpulse.db"
if not sqlite_path.exists():
    print(f"ERROR: SQLite database not found at {sqlite_path}")
    sys.exit(1)

print(f"Source:      {sqlite_path}")
print(f"Destination: {DATABASE_URL.split('@')[-1]}")
print()

# --------------------------------------------------------
# Connect
# --------------------------------------------------------
sqlite_conn = sqlite3.connect(str(sqlite_path))
sqlite_conn.row_factory = sqlite3.Row

pg_engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def migrate_table(table: str, rows, insert_sql: str, pg_conn):
    skipped = 0
    inserted = 0
    for row in rows:
        try:
            pg_conn.execute(text(insert_sql), dict(row))
            inserted += 1
        except Exception as e:
            if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
                skipped += 1
            else:
                print(f"  WARNING [{table}]: {e}")
    return inserted, skipped


with pg_engine.begin() as pg:
    cursor = sqlite_conn.cursor()

    # --------------------------------------------------------
    # users
    # --------------------------------------------------------
    cursor.execute("SELECT id, name, email, password_hash, role FROM users")
    rows = cursor.fetchall()
    ins, skp = migrate_table("users", rows,
        "INSERT INTO users (id, name, email, password_hash, role) "
        "VALUES (:id, :name, :email, :password_hash, :role) ON CONFLICT DO NOTHING",
        pg)
    print(f"users:                  inserted={ins}, skipped={skp}")

    # --------------------------------------------------------
    # complaints
    # --------------------------------------------------------
    cursor.execute("""
        SELECT id, description, category, state, location, language, status,
               latitude, longitude, location_accuracy, location_captured_at,
               created_by, created_at, updated_at,
               user_selected_category, category_source,
               ai_confidence, ai_analysis_id, ai_needs_review
        FROM complaints
    """)
    rows = cursor.fetchall()
    ins2, skp2 = migrate_table("complaints", rows,
        """INSERT INTO complaints
            (id, description, category, state, location, language, status,
             latitude, longitude, location_accuracy, location_captured_at,
             created_by, created_at, updated_at,
             user_selected_category, category_source,
             ai_confidence, ai_analysis_id, ai_needs_review)
           VALUES
            (:id, :description, :category, :state, :location, :language, :status,
             :latitude, :longitude, :location_accuracy, :location_captured_at,
             :created_by, :created_at, :updated_at,
             :user_selected_category, :category_source,
             :ai_confidence, :ai_analysis_id, :ai_needs_review)
           ON CONFLICT DO NOTHING""",
        pg)
    print(f"complaints:             inserted={ins2}, skipped={skp2}")

    # --------------------------------------------------------
    # complaint_votes
    # --------------------------------------------------------
    cursor.execute("SELECT id, complaint_id, voter_id, created_at FROM complaint_votes")
    rows = cursor.fetchall()
    ins3, skp3 = migrate_table("complaint_votes", rows,
        "INSERT INTO complaint_votes (id, complaint_id, voter_id, created_at) "
        "VALUES (:id, :complaint_id, :voter_id, :created_at) ON CONFLICT DO NOTHING",
        pg)
    print(f"complaint_votes:        inserted={ins3}, skipped={skp3}")

    # --------------------------------------------------------
    # complaint_evidence
    # --------------------------------------------------------
    cursor.execute("SELECT id, complaint_id, file_path, file_type, uploaded_at FROM complaint_evidence")
    rows = cursor.fetchall()
    ins4, skp4 = migrate_table("complaint_evidence", rows,
        "INSERT INTO complaint_evidence (id, complaint_id, file_path, file_type, uploaded_at) "
        "VALUES (:id, :complaint_id, :file_path, :file_type, :uploaded_at) ON CONFLICT DO NOTHING",
        pg)
    print(f"complaint_evidence:     inserted={ins4}, skipped={skp4}")

    # --------------------------------------------------------
    # report_ai_analyses
    # --------------------------------------------------------
    cursor.execute("""
        SELECT id, user_id, text_sha256, image_sha256, suggested_category, confidence,
               needs_review, detected_language, short_reason, text_image_consistent,
               provider, model, prompt_version, created_at, expires_at
        FROM report_ai_analyses
    """)
    rows = cursor.fetchall()
    ins5, skp5 = migrate_table("report_ai_analyses", rows,
        """INSERT INTO report_ai_analyses
            (id, user_id, text_sha256, image_sha256, suggested_category, confidence,
             needs_review, detected_language, short_reason, text_image_consistent,
             provider, model, prompt_version, created_at, expires_at)
           VALUES
            (:id, :user_id, :text_sha256, :image_sha256, :suggested_category, :confidence,
             :needs_review, :detected_language, :short_reason, :text_image_consistent,
             :provider, :model, :prompt_version, :created_at, :expires_at)
           ON CONFLICT DO NOTHING""",
        pg)
    print(f"report_ai_analyses:     inserted={ins5}, skipped={skp5}")

    # --------------------------------------------------------
    # Sync sequences so next INSERT gets the right ID
    # --------------------------------------------------------
    for tbl in ("users", "complaints", "complaint_votes", "complaint_evidence"):
        pg.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {tbl}), 0) + 1, false)"
        ))

sqlite_conn.close()
print()
print("Migration complete.")
