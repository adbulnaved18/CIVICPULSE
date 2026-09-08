import os
from pathlib import Path
import sqlite3

# ============================================================
# SQLALCHEMY (PostgreSQL) — optional, used only when
# DATABASE_URL is set to a postgresql:// connection string.
# All existing SQLite code below is fully preserved.
# ============================================================

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker, declarative_base
    _SA_AVAILABLE = True
except ImportError:
    _SA_AVAILABLE = False

Base = None
_pg_engine = None
_PgSession = None

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if _SA_AVAILABLE and DATABASE_URL.startswith("postgresql"):
    _pg_engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    _PgSession = sessionmaker(bind=_pg_engine, autocommit=False, autoflush=False)
    from sqlalchemy.orm import declarative_base as _db
    Base = _db()


def get_pg_session():
    """
    Yield a SQLAlchemy session for PostgreSQL.
    Only works when DATABASE_URL is configured.
    Raises RuntimeError if PostgreSQL is not configured.
    """
    if _PgSession is None:
        raise RuntimeError(
            "PostgreSQL is not configured. Set DATABASE_URL=postgresql://... in your environment."
        )
    session = _PgSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def is_postgres_configured() -> bool:
    """Return True when a PostgreSQL DATABASE_URL is set and SQLAlchemy is available."""
    return _pg_engine is not None

def _init_postgres_extensions():
    """Create necessary PostgreSQL extensions if they don't exist."""
    if not is_postgres_configured():
        return
    try:
        with _pg_engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Could not initialize PostgreSQL extensions: %s", exc)


# ============================================================
# PROJECT PATHS
# ============================================================

def _resolve_paths():
    # 0. Custom env var for persistent storage (e.g. Render / Docker disk)
    env_db = os.environ.get("SQLITE_DB_PATH") or os.environ.get("DATABASE_PATH")
    if env_db:
        p_db = Path(env_db).resolve()
        p_dir = p_db.parent
        schema_cand = p_dir / "schema.sql"
        if not schema_cand.exists():
            for parent in Path(__file__).resolve().parents:
                cand = parent / "database" / "schema.sql"
                if cand.exists():
                    schema_cand = cand
                    break
        return p_dir, p_db, schema_cand

    # 1. Direct candidate from file hierarchy
    for parent in Path(__file__).resolve().parents:
        db_cand = parent / "database" / "civicpulse.db"
        schema_cand = parent / "database" / "schema.sql"
        if schema_cand.exists() or db_cand.exists():
            return parent / "database", db_cand, schema_cand
    
    # 2. Candidate from current working directory
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        db_cand = parent / "database" / "civicpulse.db"
        schema_cand = parent / "database" / "schema.sql"
        if schema_cand.exists() or db_cand.exists():
            return parent / "database", db_cand, schema_cand

    base_dir = Path(__file__).resolve().parents[2]
    db_dir = base_dir / "database"
    return db_dir, db_dir / "civicpulse.db", db_dir / "schema.sql"

DATABASE_DIR, DB_PATH, SCHEMA_PATH = _resolve_paths()


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db():
    """
    Create and return a SQLite database connection.
    """

    DATABASE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    db = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,
        timeout=30.0,
    )

    db.row_factory = sqlite3.Row

    # Enable foreign key constraints and WAL mode for concurrency
    db.execute(
        "PRAGMA foreign_keys = ON"
    )
    db.execute(
        "PRAGMA journal_mode = WAL"
    )

    return db


# ============================================================
# INITIAL DATABASE
# ============================================================

def init_db():
    """
    Create the base database structure from schema.sql.
    """

    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Database schema not found: {SCHEMA_PATH}"
        )

    db = get_db()

    try:
        with open(
            SCHEMA_PATH,
            "r",
            encoding="utf-8",
        ) as file:
            schema = file.read()

        db.executescript(schema)
        db.commit()

    finally:
        db.close()


# ============================================================
# STATUS COLUMN
# ============================================================

def add_status_column():
    """
    Add complaint status column if it does not already exist.
    """

    db = get_db()

    try:
        cursor = db.cursor()

        cursor.execute(
            """
            PRAGMA table_info(complaints)
            """
        )

        columns = [
            row["name"]
            for row in cursor.fetchall()
        ]

        if "status" not in columns:
            cursor.execute(
                """
                ALTER TABLE complaints
                ADD COLUMN status TEXT DEFAULT 'Pending'
                """
            )

            db.commit()

    finally:
        db.close()


# ============================================================
# COMPLAINT VOTES TABLE
# ============================================================

def init_votes_table():
    """
    Create complaint voting table if it does not exist.

    This table is ONLY for normal complaint support votes.
    It is intentionally separate from participatory budgeting.
    """

    db = get_db()

    try:
        cursor = db.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS complaint_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                complaint_id INTEGER NOT NULL,

                voter_id TEXT NOT NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                UNIQUE (
                    complaint_id,
                    voter_id
                ),

                FOREIGN KEY (
                    complaint_id
                )
                REFERENCES complaints(id)
                ON DELETE CASCADE
            )
            """
        )

        db.commit()

    finally:
        db.close()


# ============================================================
# PARTICIPATORY BUDGETING PRIORITY TABLE
# ============================================================

def init_participatory_priority_table():
    """
    Create the participatory budgeting priority table.

    This table is intentionally separate from complaint_votes.

    complaint_votes:
        Normal "+1 Support this issue"

    participatory_priorities / participatory_priority_votes:
        Citizen's selection of an issue as a budgeting priority.
    """

    db = get_db()

    try:
        cursor = db.cursor()

        # Primary table used by participatory_budgeting.py and schema.sql
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS participatory_priorities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                issue_id INTEGER NOT NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                UNIQUE (
                    user_id,
                    issue_id
                ),

                FOREIGN KEY (
                    user_id
                )
                REFERENCES users(id)
                ON DELETE CASCADE,

                FOREIGN KEY (
                    issue_id
                )
                REFERENCES complaints(id)
                ON DELETE CASCADE
            )
            """
        )

        # Legacy alias table for backward compatibility
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS participatory_priority_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                complaint_id INTEGER NOT NULL,

                citizen_id INTEGER NOT NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                UNIQUE (
                    complaint_id,
                    citizen_id
                ),

                FOREIGN KEY (
                    complaint_id
                )
                REFERENCES complaints(id)
                ON DELETE CASCADE,

                FOREIGN KEY (
                    citizen_id
                )
                REFERENCES users(id)
                ON DELETE CASCADE
            )
            """
        )

        db.commit()

    finally:
        db.close()


# ============================================================
# EVIDENCE TABLE
# ============================================================

def init_evidence_table():
    """
    Create complaint evidence table if it does not exist.
    """

    db = get_db()

    try:
        cursor = db.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS complaint_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                complaint_id INTEGER NOT NULL,

                file_path TEXT NOT NULL,

                file_type TEXT,

                uploaded_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (
                    complaint_id
                )
                REFERENCES complaints(id)
                ON DELETE CASCADE
            )
            """
        )

        db.commit()

    finally:
        db.close()


# ============================================================
# USERS TABLE
# ============================================================

def init_users_table():
    """
    Create the users table if it does not exist.
    """

    db = get_db()

    try:
        cursor = db.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL,

                email TEXT NOT NULL UNIQUE,

                password_hash TEXT NOT NULL,

                role TEXT NOT NULL DEFAULT 'citizen'
            )
            """
        )

        db.commit()

    finally:
        db.close()


# ============================================================
# DATABASE INITIALIZATION HELPER
# ============================================================

def initialize_database():
    """
    Run all required database initialization steps.

    Order matters:
    users and complaints must exist before tables that
    reference them with foreign keys.
    """

    if is_postgres_configured():
        _init_postgres_extensions()

    init_db()

    # Make sure required base tables exist.
    init_users_table()

    add_status_column()

    add_location_columns()

    init_votes_table()

    init_evidence_table()

    init_participatory_priority_table()

    # AI-related migrations (idempotent — safe on existing databases).
    add_ai_columns_to_complaints()

    init_ai_analyses_table()


# ============================================================
# LOCATION COLUMNS
# ============================================================

def add_location_columns():
    """
    Add geo-location columns to the complaints table
    if they do not already exist.
    """

    db = get_db()

    try:
        cursor = db.cursor()

        cursor.execute(
            """
            PRAGMA table_info(complaints)
            """
        )

        columns = [
            row["name"]
            for row in cursor.fetchall()
        ]

        new_columns = {
            "state": "TEXT DEFAULT 'Other'",
            "latitude": "REAL",
            "longitude": "REAL",
            "location_accuracy": "REAL",
            "location_captured_at": "TEXT",
            "embedding_json": "TEXT",
            "embedding_model": "TEXT",
            "embedding_created_at": "TEXT",
            "embedding_version": "TEXT",
        }

        for column_name, column_type in new_columns.items():
            if column_name not in columns:
                cursor.execute(
                    f"""
                    ALTER TABLE complaints
                    ADD COLUMN {column_name} {column_type}
                    """
                )

        db.commit()

    finally:
        db.close()


# ============================================================
# AI AUDIT COLUMNS ON COMPLAINTS
# ============================================================

def add_ai_columns_to_complaints():
    """
    Add AI audit columns to the complaints table if they do not
    already exist.  Idempotent — safe to run on existing databases.
    """

    db = get_db()

    try:
        cursor = db.cursor()

        cursor.execute(
            """
            PRAGMA table_info(complaints)
            """
        )

        columns = [
            row["name"]
            for row in cursor.fetchall()
        ]

        ai_columns = {
            "user_selected_category": "TEXT",
            "category_source": "TEXT DEFAULT 'manual'",
            "ai_confidence": "REAL",
            "ai_analysis_id": "TEXT",
            "ai_needs_review": "INTEGER DEFAULT 0",
        }

        for column_name, column_type in ai_columns.items():
            if column_name not in columns:
                cursor.execute(
                    f"""
                    ALTER TABLE complaints
                    ADD COLUMN {column_name} {column_type}
                    """
                )

        db.commit()

    finally:
        db.close()


# ============================================================
# AI ANALYSES TABLE
# ============================================================

def init_ai_analyses_table():
    """
    Create the AI analysis audit table if it does not exist.
    Raw audio and image bytes are NOT stored here.
    """

    db = get_db()

    try:
        cursor = db.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS report_ai_analyses (
                id TEXT PRIMARY KEY,

                user_id INTEGER NOT NULL,

                text_sha256 TEXT NOT NULL,

                image_sha256 TEXT,

                suggested_category TEXT NOT NULL,

                confidence REAL NOT NULL,

                needs_review INTEGER NOT NULL DEFAULT 0,

                detected_language TEXT,

                short_reason TEXT,

                text_image_consistent INTEGER,

                provider TEXT NOT NULL,

                model TEXT NOT NULL,

                prompt_version TEXT NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                expires_at TIMESTAMP,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
            """
        )

        db.commit()

    finally:
        db.close()