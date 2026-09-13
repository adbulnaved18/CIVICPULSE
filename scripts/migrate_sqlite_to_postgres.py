#!/usr/bin/env python3
"""
CivicPulse — SQLite to PostgreSQL & Supabase Storage Migration Script
=====================================================================

Usage:
    python scripts/migrate_sqlite_to_postgres.py [--dry-run] [--yes]

Flags:
    --dry-run   Preflight check only: validates connectivity, schema, conflicts,
                image file existence, and Storage bucket access without modifying
                any data. Exits nonzero if any check fails.
    --yes       Skip interactive confirmation prompt.

Requires:
    DATABASE_URL=postgresql://user:password@host:port/dbname (in env or .env)
Optional for evidence migration to Supabase Storage:
    SUPABASE_URL=https://<project-ref>.supabase.co
    SUPABASE_SERVICE_KEY=<service-role-key>
    SUPABASE_STORAGE_BUCKET=evidence (defaults to 'evidence')
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import sqlite3
from pathlib import Path

# --------------------------------------------------------
# Load .env if present (must be first)
# --------------------------------------------------------
try:
    from dotenv import load_dotenv
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env", override=False)
except ImportError:
    project_root = Path(__file__).resolve().parents[1]

# --------------------------------------------------------
# Import SQLAlchemy text at module level
# --------------------------------------------------------
try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("ERROR: sqlalchemy not installed. Run: pip install sqlalchemy psycopg2-binary")
    sys.exit(1)


def _mask_url(url: str) -> str:
    """Mask password and service keys in connection strings for safe logging."""
    # postgresql://user:PASSWORD@host:port/db
    masked = re.sub(r"(://[^:]+:)([^@]+)(@)", r"\1***\3", url)
    return masked


def parse_args():
    parser = argparse.ArgumentParser(
        description="Migrate CivicPulse data from SQLite to PostgreSQL & Supabase Storage."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preflight only: validate everything without writing any data.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Bypass interactive confirmation prompt.",
    )
    return parser.parse_args()


def check_table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def migrate_table(
    table: str,
    rows,
    insert_sql: str,
    pk_col: str,
    check_sql: str,
    compare_keys: list,
    pg_conn,
    dry_run: bool = False,
    unique_checks: list[tuple[str, list[str]]] | None = None,
):
    """
    Insert rows into PostgreSQL with full conflict detection.

    Returns:
        (inserted, already_present, conflicting, failed)

    Conflict policy:
        - If destination row with same PK is identical → already_present.
        - If destination row with same PK has different fields → STOP with error.
        - If destination row has matching unique constraint under a different PK
          (e.g., matching email under a different user ID) → STOP with error.
        - If insertion fails → STOP with error. An insertion error is never counted
          as already_present and PostgreSQL transactions cannot continue after an error.
        - If no existing row → insert.
    """
    inserted = 0
    already_present = 0
    conflicting = 0
    failed = 0

    for row in rows:
        row_dict = dict(row)
        pk_val = row_dict.get(pk_col)

        if dry_run:
            inserted += 1
            continue

        # Check if PK already exists in destination
        try:
            existing = pg_conn.execute(text(check_sql), {pk_col: pk_val}).fetchone()
        except Exception as e:
            raise RuntimeError(
                f"Failed to check existing row in [{table}] PK={pk_val}: {e}\n"
                "Stopping migration to prevent partial data."
            ) from e

        if existing is not None:
            existing_dict = dict(existing._mapping)
            # Compare relevant fields
            mismatch = False
            for k in compare_keys:
                src_val = row_dict.get(k)
                dst_val = existing_dict.get(k)
                # Normalize None/empty for comparison
                if str(src_val or "").strip() != str(dst_val or "").strip():
                    mismatch = True
                    print(
                        f"  CONFLICT [{table}] PK={pk_val} field='{k}' "
                        f"src={repr(src_val)} dst={repr(dst_val)}"
                    )
                    break
            if mismatch:
                conflicting += 1
                raise RuntimeError(
                    f"Conflicting record in [{table}] at PK={pk_val}. "
                    "Stopping migration to prevent data corruption. "
                    "Resolve the conflict manually before rerunning."
                )
            else:
                already_present += 1
            continue

        # Check unique constraints when PK was not found
        if unique_checks:
            for u_sql, u_keys in unique_checks:
                params = {k: row_dict.get(k) for k in u_keys}
                if any(params.get(k) is None for k in u_keys):
                    continue
                try:
                    u_existing = pg_conn.execute(text(u_sql), params).fetchone()
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to check unique constraint in [{table}]: {e}\n"
                        "Stopping migration to prevent partial data."
                    ) from e
                if u_existing is not None:
                    u_dict = dict(u_existing._mapping)
                    dst_pk = u_dict.get(pk_col)
                    conflicting += 1
                    raise RuntimeError(
                        f"Conflicting record in [{table}]: unique constraint ({', '.join(f'{k}={repr(params[k])}' for k in u_keys)}) "
                        f"already exists in destination under different {pk_col}={dst_pk} (source {pk_col}={pk_val}). "
                        "Matching a unique key under a different ID is not a safely migrated record."
                    )

        try:
            pg_conn.execute(text(insert_sql), row_dict)
            inserted += 1
        except Exception as e:
            failed += 1
            raise RuntimeError(
                f"Failed to insert into [{table}] PK={pk_val}: {e}\n"
                "Stopping migration: insertion error cannot be treated as already present, "
                "and PostgreSQL cannot continue in an aborted transaction."
            ) from e

    return inserted, already_present, conflicting, failed


def _make_migration_evidence_key(complaint_id: int, evidence_id: int, file_path: str) -> str:
    """Deterministic, stable key for migrated evidence objects."""
    path_hash = hashlib.sha256(file_path.encode()).hexdigest()[:12]
    return f"evidence/{complaint_id}/migrated_{evidence_id}_{path_hash}"


def _check_destination_evidence_exists(pg_conn, evidence_id: int) -> str | None:
    """Return stored file_path for an evidence row already in destination, or None."""
    try:
        row = pg_conn.execute(
            text("SELECT file_path FROM complaint_evidence WHERE id = :id"),
            {"id": evidence_id},
        ).fetchone()
        if row:
            return row[0]
    except Exception:
        pass
    return None


def main():
    args = parse_args()

    sys.path.insert(0, str(project_root))
    try:
        from backend.app.services import storage
        _storage_available = True
    except Exception:
        storage = None
        _storage_available = False

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        print("ERROR: DATABASE_URL must be set and start with 'postgresql://'")
        print("  Example: DATABASE_URL=postgresql://user:password@host:5432/dbname")
        sys.exit(1)

    sqlite_path = project_root / "database" / "civicpulse.db"
    if not sqlite_path.exists():
        print(f"ERROR: SQLite database not found at {sqlite_path}")
        sys.exit(1)

    print("=" * 60)
    print("CivicPulse Data Migration")
    print("=" * 60)
    print(f"Source (SQLite):  {sqlite_path}")
    print(f"Destination (PG): {_mask_url(database_url).split('@')[-1]}")
    print(f"Dry Run Mode:     {args.dry_run}")
    storage_active = _storage_available and storage.is_storage_configured()
    print(f"Supabase Storage: {'CONFIGURED' if storage_active else 'NOT CONFIGURED (file paths preserved)'}")
    print("=" * 60)

    # --------------------------------------------------------
    # DRY-RUN PREFLIGHT CHECKS
    # --------------------------------------------------------
    if args.dry_run:
        print("\n[DRY-RUN] Running preflight checks — no data will be written.\n")
        preflight_errors = []

        # 1. Source schema
        print("[1/5] Checking source SQLite schema...")
        try:
            sq_conn = sqlite3.connect(str(sqlite_path))
            sq_conn.row_factory = sqlite3.Row
            sq_cur = sq_conn.cursor()
            required_tables = ["users", "complaints", "complaint_votes", "complaint_evidence"]
            for tbl in required_tables:
                if not check_table_exists(sq_cur, tbl):
                    preflight_errors.append(f"  MISSING source table: {tbl}")
                    print(f"  ✗ Table '{tbl}' not found in SQLite source")
                else:
                    print(f"  ✓ Table '{tbl}' present")
        except Exception as e:
            preflight_errors.append(f"  Cannot open SQLite source: {e}")
            print(f"  ✗ Cannot open SQLite source: {e}")
            sq_conn = None

        # 2. Destination connectivity & schema
        print("\n[2/5] Checking PostgreSQL destination connectivity...")
        try:
            pg_engine = create_engine(database_url, pool_pre_ping=True)
            with pg_engine.connect() as pg_conn:
                pg_conn.execute(text("SELECT 1"))
                print("  ✓ Connected to PostgreSQL")
                for tbl in required_tables:
                    try:
                        pg_conn.execute(text(f"SELECT 1 FROM {tbl} LIMIT 1"))
                        print(f"  ✓ Table '{tbl}' exists in destination")
                    except Exception as e:
                        preflight_errors.append(f"  Destination table missing: {tbl} ({e})")
                        print(f"  ✗ Table '{tbl}' missing in destination: {e}")
        except Exception as e:
            preflight_errors.append(f"  Cannot connect to PostgreSQL: {e}")
            print(f"  ✗ Cannot connect to PostgreSQL: {_mask_url(str(e))}")
            pg_engine = None

        # 3. Conflict detection across all tables
        if sq_conn and pg_engine:
            print("\n[3/5] Checking for record conflicts across all migrated tables...")
            try:
                with pg_engine.connect() as pg_conn:
                    # 3a. users
                    sq_cur.execute("SELECT id, name, email FROM users")
                    users = sq_cur.fetchall()
                    user_conflicts = 0
                    for u in users:
                        dst = pg_conn.execute(
                            text("SELECT id, email FROM users WHERE id = :id"), {"id": u[0]}
                        ).fetchone()
                        if dst and dst[1] != u[2]:
                            user_conflicts += 1
                            preflight_errors.append(
                                f"  CONFLICT users id={u[0]}: src_email={u[2]} dst_email={dst[1]}"
                            )
                            print(f"  ✗ CONFLICT users id={u[0]}")
                        # Check unique email under different ID
                        dst_by_email = pg_conn.execute(
                            text("SELECT id, email FROM users WHERE email = :email"), {"email": u[2]}
                        ).fetchone()
                        if dst_by_email and dst_by_email[0] != u[0]:
                            user_conflicts += 1
                            preflight_errors.append(
                                f"  CONFLICT users email={u[2]}: exists in dest as id={dst_by_email[0]}, but source id={u[0]}"
                            )
                            print(f"  ✗ CONFLICT users email={u[2]} (id mismatch)")
                    if user_conflicts == 0:
                        print(f"  ✓ Checked {len(users)} users — no conflicts")

                    # 3b. complaints
                    sq_cur.execute("SELECT id, description, category FROM complaints")
                    complaints = sq_cur.fetchall()
                    complaint_conflicts = 0
                    for c in complaints:
                        dst_c = pg_conn.execute(
                            text("SELECT id, description, category FROM complaints WHERE id = :id"), {"id": c[0]}
                        ).fetchone()
                        if dst_c:
                            if str(dst_c[1] or "").strip() != str(c[1] or "").strip() or str(dst_c[2] or "").strip() != str(c[2] or "").strip():
                                complaint_conflicts += 1
                                preflight_errors.append(
                                    f"  CONFLICT complaints id={c[0]}: description or category differs"
                                )
                                print(f"  ✗ CONFLICT complaints id={c[0]}")
                    if complaint_conflicts == 0:
                        print(f"  ✓ Checked {len(complaints)} complaints — no conflicts")

                    # 3c. complaint_votes
                    sq_cur.execute("SELECT id, complaint_id, voter_id FROM complaint_votes")
                    votes = sq_cur.fetchall()
                    vote_conflicts = 0
                    for v in votes:
                        dst_v = pg_conn.execute(
                            text("SELECT id, complaint_id, voter_id FROM complaint_votes WHERE id = :id"), {"id": v[0]}
                        ).fetchone()
                        if dst_v:
                            if dst_v[1] != v[1] or str(dst_v[2]) != str(v[2]):
                                vote_conflicts += 1
                                preflight_errors.append(
                                    f"  CONFLICT complaint_votes id={v[0]}: fields differ"
                                )
                                print(f"  ✗ CONFLICT complaint_votes id={v[0]}")
                        dst_uv = pg_conn.execute(
                            text("SELECT id, complaint_id, voter_id FROM complaint_votes WHERE complaint_id = :cid AND voter_id = :vid"),
                            {"cid": v[1], "vid": v[2]}
                        ).fetchone()
                        if dst_uv and dst_uv[0] != v[0]:
                            vote_conflicts += 1
                            preflight_errors.append(
                                f"  CONFLICT complaint_votes (complaint_id={v[1]}, voter_id={v[2]}): exists under id={dst_uv[0]} vs source id={v[0]}"
                            )
                            print(f"  ✗ CONFLICT complaint_votes unique key (cid={v[1]}, vid={v[2]})")
                    if vote_conflicts == 0:
                        print(f"  ✓ Checked {len(votes)} complaint votes — no conflicts")

                    # 3d. complaint_evidence
                    sq_cur.execute("SELECT id, complaint_id, file_path FROM complaint_evidence")
                    ev_recs = sq_cur.fetchall()
                    ev_conflicts = 0
                    for ev in ev_recs:
                        dst_ev = pg_conn.execute(
                            text("SELECT id, complaint_id FROM complaint_evidence WHERE id = :id"), {"id": ev[0]}
                        ).fetchone()
                        if dst_ev and dst_ev[1] != ev[1]:
                            ev_conflicts += 1
                            preflight_errors.append(
                                f"  CONFLICT complaint_evidence id={ev[0]}: complaint_id differs"
                            )
                            print(f"  ✗ CONFLICT complaint_evidence id={ev[0]}")
                    if ev_conflicts == 0:
                        print(f"  ✓ Checked {len(ev_recs)} complaint evidence records — no conflicts")

                    # 3e. participatory_priorities
                    if check_table_exists(sq_cur, "participatory_priorities"):
                        sq_cur.execute("SELECT id, user_id, issue_id FROM participatory_priorities")
                        pp_recs = sq_cur.fetchall()
                        pp_conflicts = 0
                        for pp in pp_recs:
                            dst_pp = pg_conn.execute(
                                text("SELECT id, user_id, issue_id FROM participatory_priorities WHERE id = :id"), {"id": pp[0]}
                            ).fetchone()
                            if dst_pp and (dst_pp[1] != pp[1] or dst_pp[2] != pp[2]):
                                pp_conflicts += 1
                                preflight_errors.append(
                                    f"  CONFLICT participatory_priorities id={pp[0]}: fields differ"
                                )
                                print(f"  ✗ CONFLICT participatory_priorities id={pp[0]}")
                            dst_upp = pg_conn.execute(
                                text("SELECT id FROM participatory_priorities WHERE user_id = :uid AND issue_id = :iid"),
                                {"uid": pp[1], "iid": pp[2]}
                            ).fetchone()
                            if dst_upp and dst_upp[0] != pp[0]:
                                pp_conflicts += 1
                                preflight_errors.append(
                                    f"  CONFLICT participatory_priorities unique key (user={pp[1]}, issue={pp[2]}): exists under id={dst_upp[0]}"
                                )
                                print(f"  ✗ CONFLICT participatory_priorities unique key (user={pp[1]}, issue={pp[2]})")
                        if pp_conflicts == 0:
                            print(f"  ✓ Checked {len(pp_recs)} participatory priorities — no conflicts")

                    # 3f. participatory_priority_votes
                    if check_table_exists(sq_cur, "participatory_priority_votes"):
                        sq_cur.execute("SELECT id, complaint_id, citizen_id FROM participatory_priority_votes")
                        ppv_recs = sq_cur.fetchall()
                        ppv_conflicts = 0
                        for ppv in ppv_recs:
                            dst_ppv = pg_conn.execute(
                                text("SELECT id, complaint_id, citizen_id FROM participatory_priority_votes WHERE id = :id"), {"id": ppv[0]}
                            ).fetchone()
                            if dst_ppv and (dst_ppv[1] != ppv[1] or dst_ppv[2] != ppv[2]):
                                ppv_conflicts += 1
                                preflight_errors.append(
                                    f"  CONFLICT participatory_priority_votes id={ppv[0]}: fields differ"
                                )
                                print(f"  ✗ CONFLICT participatory_priority_votes id={ppv[0]}")
                            dst_uppv = pg_conn.execute(
                                text("SELECT id FROM participatory_priority_votes WHERE complaint_id = :cid AND citizen_id = :cid2"),
                                {"cid": ppv[1], "cid2": ppv[2]}
                            ).fetchone()
                            if dst_uppv and dst_uppv[0] != ppv[0]:
                                ppv_conflicts += 1
                                preflight_errors.append(
                                    f"  CONFLICT participatory_priority_votes unique key (complaint={ppv[1]}, citizen={ppv[2]}): exists under id={dst_uppv[0]}"
                                )
                                print(f"  ✗ CONFLICT participatory_priority_votes unique key")
                        if ppv_conflicts == 0:
                            print(f"  ✓ Checked {len(ppv_recs)} priority votes — no conflicts")

                    # 3g. report_ai_analyses
                    if check_table_exists(sq_cur, "report_ai_analyses"):
                        sq_cur.execute("SELECT id, user_id, text_sha256 FROM report_ai_analyses")
                        ai_recs = sq_cur.fetchall()
                        ai_conflicts = 0
                        for ai in ai_recs:
                            dst_ai = pg_conn.execute(
                                text("SELECT id, user_id, text_sha256 FROM report_ai_analyses WHERE id = :id"), {"id": ai[0]}
                            ).fetchone()
                            if dst_ai and (dst_ai[1] != ai[1] or dst_ai[2] != ai[2]):
                                ai_conflicts += 1
                                preflight_errors.append(
                                    f"  CONFLICT report_ai_analyses id={ai[0]}: fields differ"
                                )
                                print(f"  ✗ CONFLICT report_ai_analyses id={ai[0]}")
                        if ai_conflicts == 0:
                            print(f"  ✓ Checked {len(ai_recs)} AI analyses — no conflicts")

            except Exception as e:
                preflight_errors.append(f"  Conflict check failed with error: {e}")
                print(f"  ✗ Could not check conflicts: {e}")

        # 4. Source image file existence
        local_evidence_count = 0
        if sq_conn:
            print("\n[4/5] Checking source evidence file availability...")
            try:
                sq_cur.execute("SELECT id, file_path FROM complaint_evidence")
                ev_rows = sq_cur.fetchall()
                missing = 0
                for ev in ev_rows:
                    fpath = ev[1] or ""
                    if fpath.startswith("evidence/") or fpath.startswith("http"):
                        continue  # already a storage key or URL
                    local_evidence_count += 1
                    lp = project_root / fpath
                    if not lp.exists():
                        alt = project_root / "backend" / fpath
                        if not alt.exists():
                            missing += 1
                            print(f"  MISSING: {fpath}")
                if missing == 0:
                    print(f"  ✓ All {len(ev_rows)} evidence file(s) located ({local_evidence_count} local to migrate)")
                else:
                    preflight_errors.append(f"  {missing} evidence file(s) missing from disk")
                    print(f"  ✗ {missing} evidence file(s) not found")
            except Exception as e:
                preflight_errors.append(f"  Could not check evidence files: {e}")
                print(f"  ✗ Could not check evidence files: {e}")

        # 5. Supabase Storage bucket access
        print("\n[5/5] Checking Supabase Storage bucket access...")
        if local_evidence_count > 0 and not storage_active:
            preflight_errors.append(
                f"  Supabase Storage is NOT configured, but {local_evidence_count} local evidence file(s) must be migrated. "
                "Supabase Storage configuration is required when migrating local evidence."
            )
            print(f"  ✗ Missing Supabase Storage configuration for {local_evidence_count} local evidence file(s).")
        elif storage_active:
            try:
                client = storage._get_supabase_client()
                buckets = client.storage.list_buckets()
                bucket_names = [b.name if hasattr(b, "name") else str(b) for b in buckets]
                bucket_name = os.environ.get("SUPABASE_STORAGE_BUCKET", "evidence")
                if bucket_name in bucket_names:
                    print(f"  ✓ Bucket '{bucket_name}' accessible")
                else:
                    preflight_errors.append(f"  Bucket '{bucket_name}' not found. Available: {bucket_names}")
                    print(f"  ✗ Bucket '{bucket_name}' not found. Available: {bucket_names}")
            except Exception as e:
                preflight_errors.append(f"  Cannot access Supabase Storage: {e}")
                print(f"  ✗ Cannot access Supabase Storage: {e}")
        else:
            print("  ✓ No local evidence files need migration; Supabase Storage not required.")

        if sq_conn:
            sq_conn.close()

        print("\n" + "=" * 60)
        if preflight_errors:
            print("[DRY-RUN] PREFLIGHT FAILED — issues found:")
            for err in preflight_errors:
                print(err)
            sys.exit(1)
        else:
            print("[DRY-RUN] PREFLIGHT PASSED — migration is safe to run without --dry-run.")
            sys.exit(0)

    # --------------------------------------------------------
    # INTERACTIVE CONFIRMATION (real migration)
    # --------------------------------------------------------
    if not args.yes:
        confirm = input("\nHave you backed up your data? Proceed with migration? (yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            print("Migration aborted by user.")
            sys.exit(0)

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()

    pg_engine = create_engine(database_url, pool_pre_ping=True)

    # Track storage objects created this run for rollback on failure
    created_storage_keys: list[str] = []

    with pg_engine.connect() as pg_conn:
        trans = pg_conn.begin()
        try:
            # ----------------------------------------------------
            # 1. users
            # ----------------------------------------------------
            cursor.execute("SELECT id, name, email, password_hash, role FROM users")
            rows = cursor.fetchall()
            ins, pres, conf, fail = migrate_table(
                "users", rows,
                "INSERT INTO users (id, name, email, password_hash, role) "
                "VALUES (:id, :name, :email, :password_hash, :role)",
                pk_col="id",
                check_sql="SELECT id, email FROM users WHERE id = :id",
                compare_keys=["email"],
                pg_conn=pg_conn,
                unique_checks=[("SELECT id, email FROM users WHERE email = :email", ["email"])],
            )
            print(f"users:                  {len(rows)} source | inserted={ins}, already_present={pres}, conflicting={conf}, failed={fail}")

            # ----------------------------------------------------
            # 2. complaints
            # ----------------------------------------------------
            cursor.execute("""
                SELECT id, description, category, state, location, language, status,
                       latitude, longitude, location_accuracy, location_captured_at,
                       created_by, created_at, updated_at,
                       user_selected_category, category_source,
                       ai_confidence, ai_analysis_id, ai_needs_review
                FROM complaints
            """)
            rows = cursor.fetchall()
            ins2, pres2, conf2, fail2 = migrate_table(
                "complaints", rows,
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
                     :ai_confidence, :ai_analysis_id, :ai_needs_review)""",
                pk_col="id",
                check_sql="SELECT id, description, category FROM complaints WHERE id = :id",
                compare_keys=["description", "category"],
                pg_conn=pg_conn,
            )
            print(f"complaints:             {len(rows)} source | inserted={ins2}, already_present={pres2}, conflicting={conf2}, failed={fail2}")

            # ----------------------------------------------------
            # 3. complaint_votes
            # ----------------------------------------------------
            cursor.execute("SELECT id, complaint_id, voter_id, created_at FROM complaint_votes")
            rows = cursor.fetchall()
            ins3, pres3, conf3, fail3 = migrate_table(
                "complaint_votes", rows,
                "INSERT INTO complaint_votes (id, complaint_id, voter_id, created_at) "
                "VALUES (:id, :complaint_id, :voter_id, :created_at)",
                pk_col="id",
                check_sql="SELECT id, voter_id, complaint_id FROM complaint_votes WHERE id = :id",
                compare_keys=["voter_id", "complaint_id"],
                pg_conn=pg_conn,
                unique_checks=[("SELECT id, complaint_id, voter_id FROM complaint_votes WHERE complaint_id = :complaint_id AND voter_id = :voter_id", ["complaint_id", "voter_id"])],
            )
            print(f"complaint_votes:        {len(rows)} source | inserted={ins3}, already_present={pres3}, conflicting={conf3}, failed={fail3}")

            # ----------------------------------------------------
            # 4. complaint_evidence (with Storage migration)
            # ----------------------------------------------------
            cursor.execute("SELECT id, complaint_id, file_path, file_type, uploaded_at FROM complaint_evidence")
            rows = cursor.fetchall()
            evidence_rows = []
            files_uploaded = 0
            files_reused = 0
            missing_files = 0

            for r in rows:
                r_dict = dict(r)
                fpath = r_dict.get("file_path", "")
                ev_id = r_dict["id"]
                cid = r_dict["complaint_id"]

                # If storage is active and path is a local path, migrate to Storage
                if (
                    storage_active
                    and fpath
                    and not fpath.startswith("http://")
                    and not fpath.startswith("https://")
                    and not fpath.startswith("evidence/")
                ):
                    # Check if already present in destination
                    existing_key = _check_destination_evidence_exists(pg_conn, ev_id)
                    if existing_key:
                        r_dict["file_path"] = existing_key
                        files_reused += 1
                    else:
                        # Deterministic key
                        new_key = _make_migration_evidence_key(cid, ev_id, fpath)
                        local_candidate = project_root / fpath
                        if not local_candidate.exists():
                            alt = project_root / "backend" / fpath
                            if alt.exists():
                                local_candidate = alt

                        if local_candidate.exists():
                            try:
                                with open(local_candidate, "rb") as f:
                                    data = f.read()
                                storage.upload_evidence(
                                    file_bytes=data,
                                    object_key=new_key,
                                    content_type=r_dict.get("file_type") or "image/jpeg",
                                )
                                created_storage_keys.append(new_key)
                                r_dict["file_path"] = new_key
                                files_uploaded += 1
                            except Exception as up_err:
                                print(f"  WARNING: Failed to upload evidence {ev_id} ({local_candidate}): {up_err}")
                                missing_files += 1
                                print(f"  ERROR: Source image missing is treated as incomplete — exiting nonzero after migration.")
                        else:
                            missing_files += 1
                            print(f"  NOTICE: Local evidence file not found at {local_candidate}; keeping original path.")

                evidence_rows.append(r_dict)

            ins4, pres4, conf4, fail4 = migrate_table(
                "complaint_evidence", evidence_rows,
                "INSERT INTO complaint_evidence (id, complaint_id, file_path, file_type, uploaded_at) "
                "VALUES (:id, :complaint_id, :file_path, :file_type, :uploaded_at)",
                pk_col="id",
                check_sql="SELECT id, file_path, complaint_id FROM complaint_evidence WHERE id = :id",
                compare_keys=["complaint_id"],
                pg_conn=pg_conn,
            )
            print(f"complaint_evidence:     {len(rows)} source | inserted={ins4}, already_present={pres4}, conflicting={conf4}, failed={fail4} (uploaded={files_uploaded}, reused={files_reused}, missing={missing_files})")

            # ----------------------------------------------------
            # 5. participatory_priorities
            # ----------------------------------------------------
            if check_table_exists(cursor, "participatory_priorities"):
                cursor.execute("SELECT id, user_id, issue_id, created_at FROM participatory_priorities")
                pb_rows = cursor.fetchall()
                ins_pb, pres_pb, conf_pb, fail_pb = migrate_table(
                    "participatory_priorities", pb_rows,
                    "INSERT INTO participatory_priorities (id, user_id, issue_id, created_at) "
                    "VALUES (:id, :user_id, :issue_id, :created_at)",
                    pk_col="id",
                    check_sql="SELECT id, user_id, issue_id FROM participatory_priorities WHERE id = :id",
                    compare_keys=["user_id", "issue_id"],
                    pg_conn=pg_conn,
                    unique_checks=[("SELECT id, user_id, issue_id FROM participatory_priorities WHERE user_id = :user_id AND issue_id = :issue_id", ["user_id", "issue_id"])],
                )
                print(f"participatory_priorities: {len(pb_rows)} source | inserted={ins_pb}, already_present={pres_pb}, conflicting={conf_pb}, failed={fail_pb}")
            else:
                print("participatory_priorities: table not present in SQLite; skipped.")

            # ----------------------------------------------------
            # 6. participatory_priority_votes
            # ----------------------------------------------------
            if check_table_exists(cursor, "participatory_priority_votes"):
                cursor.execute("SELECT id, complaint_id, citizen_id, created_at FROM participatory_priority_votes")
                pb_vote_rows = cursor.fetchall()
                ins_pbv, pres_pbv, conf_pbv, fail_pbv = migrate_table(
                    "participatory_priority_votes", pb_vote_rows,
                    "INSERT INTO participatory_priority_votes (id, complaint_id, citizen_id, created_at) "
                    "VALUES (:id, :complaint_id, :citizen_id, :created_at)",
                    pk_col="id",
                    check_sql="SELECT id, complaint_id, citizen_id FROM participatory_priority_votes WHERE id = :id",
                    compare_keys=["complaint_id", "citizen_id"],
                    pg_conn=pg_conn,
                    unique_checks=[("SELECT id, complaint_id, citizen_id FROM participatory_priority_votes WHERE complaint_id = :complaint_id AND citizen_id = :citizen_id", ["complaint_id", "citizen_id"])],
                )
                print(f"participatory_priority_votes: {len(pb_vote_rows)} source | inserted={ins_pbv}, already_present={pres_pbv}, conflicting={conf_pbv}, failed={fail_pbv}")

            # ----------------------------------------------------
            # 7. report_ai_analyses
            # ----------------------------------------------------
            if check_table_exists(cursor, "report_ai_analyses"):
                cursor.execute("""
                    SELECT id, user_id, text_sha256, image_sha256, suggested_category, confidence,
                           needs_review, detected_language, short_reason, text_image_consistent,
                           provider, model, prompt_version, created_at, expires_at
                    FROM report_ai_analyses
                """)
                rows = cursor.fetchall()
                ins5, pres5, conf5, fail5 = migrate_table(
                    "report_ai_analyses", rows,
                    """INSERT INTO report_ai_analyses
                        (id, user_id, text_sha256, image_sha256, suggested_category, confidence,
                         needs_review, detected_language, short_reason, text_image_consistent,
                         provider, model, prompt_version, created_at, expires_at)
                       VALUES
                        (:id, :user_id, :text_sha256, :image_sha256, :suggested_category, :confidence,
                         :needs_review, :detected_language, :short_reason, :text_image_consistent,
                         :provider, :model, :prompt_version, :created_at, :expires_at)""",
                    pk_col="id",
                    check_sql="SELECT id, user_id, text_sha256 FROM report_ai_analyses WHERE id = :id",
                    compare_keys=["user_id", "text_sha256"],
                    pg_conn=pg_conn,
                )
                print(f"report_ai_analyses:     {len(rows)} source | inserted={ins5}, already_present={pres5}, conflicting={conf5}, failed={fail5}")

            # ----------------------------------------------------
            # 8. Sync sequences (real migration only)
            # ----------------------------------------------------
            sync_tables = [
                "users", "complaints", "complaint_votes", "complaint_evidence",
                "participatory_priorities", "participatory_priority_votes"
            ]
            for tbl in sync_tables:
                if not check_table_exists(cursor, tbl):
                    continue
                try:
                    pg_conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {tbl}), 0) + 1, false)"
                    ))
                except Exception as seq_err:
                    raise RuntimeError(
                        f"Failed to reset sequence for table [{tbl}]: {seq_err}\n"
                        "Stopping migration: sequence reset error cannot be ignored."
                    ) from seq_err

            # ----------------------------------------------------
            # PRE-COMMIT: abort if any evidence images were missing
            # ----------------------------------------------------
            if missing_files > 0:
                trans.rollback()
                print(f"\n[ERROR] {missing_files} evidence file(s) were missing from disk.")
                print("Migration aborted — resolve missing files before rerunning.")
                # Clean up storage objects created this run
                if created_storage_keys and storage_active:
                    print(f"Cleaning up {len(created_storage_keys)} storage object(s) created this run...")
                    for key in created_storage_keys:
                        try:
                            ok = storage.delete_evidence(key)
                            if ok:
                                print(f"  Deleted: {key}")
                            else:
                                print(f"  FAILED to delete {key} — manual cleanup required.")
                        except Exception as del_err:
                            print(f"  FAILED to delete {key}: {del_err} — manual cleanup required.")
                sys.exit(1)

            try:
                trans.commit()
                print("\n[SUCCESS] Migration committed successfully.")
            except Exception as commit_err:
                try:
                    trans.rollback()
                except Exception:
                    pass

                # Check if the migration records actually committed via a fresh connection
                records_committed = None
                try:
                    fresh_engine = create_engine(database_url, pool_pre_ping=True)
                    with fresh_engine.connect() as check_conn:
                        chk = check_conn.execute(text("SELECT COUNT(*) FROM complaints")).fetchone()
                        records_committed = (chk is not None and chk[0] > 0)
                except Exception:
                    records_committed = None

                if records_committed is True:
                    print(f"\n[WARNING] Commit encountered error ({commit_err}) but destination records exist. Storage objects will NOT be deleted.")
                elif records_committed is False:
                    # Definitely rolled back: clean up
                    if created_storage_keys and storage_active:
                        print(f"Cleaning up {len(created_storage_keys)} storage object(s) created this run...")
                        for key in created_storage_keys:
                            try:
                                ok = storage.delete_evidence(key)
                                if ok:
                                    print(f"  Deleted: {key}")
                                else:
                                    print(f"  FAILED to delete {key} — manual cleanup required.")
                            except Exception as del_err:
                                print(f"  FAILED to delete {key}: {del_err} — manual cleanup required.")
                else:
                    print(f"\n[CRITICAL] Commit outcome uncertain. Retaining {len(created_storage_keys)} storage object(s) to avoid data loss.")
                    if storage and hasattr(storage, "record_recovery_task"):
                        storage.record_recovery_task(
                            "migration_uncertain_commit_reconciliation",
                            {
                                "keys": created_storage_keys,
                                "error": str(commit_err),
                            },
                        )
                raise commit_err

            # ----------------------------------------------------
            # 9. Verification Summary
            # ----------------------------------------------------
            print("\nVerification Record Counts:")
            print(f"{'Table':<30} {'SQLite Count':<15} {'PostgreSQL Count':<15}")
            print("-" * 60)
            verify_tables = [
                "users", "complaints", "complaint_votes", "complaint_evidence",
                "participatory_priorities", "report_ai_analyses",
            ]
            for tbl in verify_tables:
                if check_table_exists(cursor, tbl):
                    cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
                    sq_cnt = cursor.fetchone()[0]
                else:
                    sq_cnt = 0
                try:
                    pg_res = pg_conn.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
                    pg_cnt = pg_res.fetchone()[0]
                except Exception:
                    pg_cnt = "N/A"
                print(f"{tbl:<30} {sq_cnt:<15} {pg_cnt:<15}")

        except Exception as e:
            try:
                trans.rollback()
            except Exception:
                pass
            print(f"\n[ERROR] Migration failed and was rolled back: {_mask_url(str(e))}")
            # Clean up storage objects created in this run
            if created_storage_keys and storage_active:
                print(f"Cleaning up {len(created_storage_keys)} storage object(s) created this run...")
                for key in created_storage_keys:
                    try:
                        ok = storage.delete_evidence(key)
                        if ok:
                            print(f"  Deleted: {key}")
                        else:
                            print(f"  FAILED to delete {key} — manual cleanup required.")
                    except Exception as del_err:
                        print(f"  FAILED to delete {key}: {del_err} — manual cleanup required.")
            raise
        finally:
            sqlite_conn.close()


if __name__ == "__main__":
    main()
