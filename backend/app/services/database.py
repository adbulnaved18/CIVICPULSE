"""
CivicPulse — Database Service
================================
Provides ``get_db()`` — the single connection factory used by every route.

Database selection
------------------
* DATABASE_URL starts with ``postgresql`` → psycopg2 connection from a
  bounded ThreadedConnectionPool (TLS required; pool_size capped for
  Render Free tier constraints).
* No DATABASE_URL (or DATABASE_URL is empty / SQLite path) → local SQLite.

An invalid / unreachable PostgreSQL URL causes a clear ``RuntimeError`` at
startup instead of silently falling back to SQLite.

SQLite helpers (``init_*`` functions) are preserved for local development
and testing.  For PostgreSQL, ``initialize_database()`` applies
``database/postgres_schema.sql`` (idempotent, ``IF NOT EXISTS`` throughout).

Connection compatibility
-------------------------
``get_db()`` always returns an object that exposes:
  .cursor()    – returns rows accessible by name AND by index
  .commit()
  .rollback()
  .close()     – for PostgreSQL this returns the connection to the pool
  .execute()   – convenience shorthand (used in ai.py)

SQL in routes uses ``?`` placeholders; the ``db_compat`` module converts
them to ``%s`` for psycopg2 transparently.

Supabase / Render connection notes
-----------------------------------
Use the *Session Pooler* URL (port 5432) from the Supabase dashboard for
persistent web services (e.g. Render):
  postgresql://postgres.[ref]:[pw]@aws-0-[region].pooler.supabase.com:5432/postgres?sslmode=require

The Session Pooler supports psycopg2 persistent connection pooling without
PgBouncer transaction-mode restrictions.  pool_size is kept small (1 min,
5 max) to stay within Supabase Free connection limits.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# SQLALCHEMY — kept for the migration script and pg_engine helpers
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

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

# Normalize postgres:// → postgresql:// (e.g. Render/Heroku-style URLs)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

if _SA_AVAILABLE and DATABASE_URL.startswith("postgresql"):
    _pg_engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=5,
        connect_args={"sslmode": "require"} if "sslmode" not in DATABASE_URL else {},
    )
    _PgSession = sessionmaker(bind=_pg_engine, autocommit=False, autoflush=False)
    from sqlalchemy.orm import declarative_base as _db
    Base = _db()


def get_pg_session():
    """
    Yield a SQLAlchemy session for PostgreSQL.
    Raises RuntimeError if PostgreSQL is not configured.
    """
    if _PgSession is None:
        raise RuntimeError(
            "PostgreSQL is not configured. "
            "Set DATABASE_URL=postgresql://... in your environment."
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
    """Return True when a PostgreSQL DATABASE_URL is set."""
    return _pg_pool is not None


# ============================================================
# PSYCOPG2 CONNECTION POOL  (initialised only when DATABASE_URL is PG)
# ============================================================

_pg_pool = None  # type: Optional[any]

if DATABASE_URL.startswith("postgresql"):
    try:
        import psycopg2  # type: ignore
        import psycopg2.pool  # type: ignore
        import psycopg2.extras  # type: ignore

        # Build DSN ensuring TLS and connection timeout are both present
        _dsn = DATABASE_URL
        if "sslmode" not in _dsn:
            _dsn = _dsn + ("&" if "?" in _dsn else "?") + "sslmode=require"
        if "connect_timeout" not in _dsn:
            _dsn = _dsn + "&connect_timeout=10"

        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=_dsn,
        )
        logger.info("PostgreSQL connection pool initialised (pool_size=1..5).")

    except ImportError as _imp_err:
        raise RuntimeError(
            "DATABASE_URL is set to a PostgreSQL URL but psycopg2 is not "
            "installed. Run: pip install psycopg2-binary"
        ) from _imp_err

    except Exception as _pg_conn_err:
        raise RuntimeError(
            f"DATABASE_URL is set to a PostgreSQL URL but the connection "
            f"failed: {_pg_conn_err}\n"
            "Fix DATABASE_URL, check network/credentials, or remove it to "
            "use SQLite for local development."
        ) from _pg_conn_err


# ============================================================
# POOLED PSYCOPG2 CONNECTION WRAPPER
# ============================================================

class _PooledPgConn:
    """
    Thin wrapper around a psycopg2 connection obtained from
    ThreadedConnectionPool.

    * ``close()`` returns the connection to the pool (not close it).
    * ``cursor()`` always uses DictCursor so rows support both index
      AND named access — matching sqlite3.Row behaviour.
    * ``execute()`` is a convenience shorthand that adapts ``?`` → ``%s``.
    """

    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn

    # ── Cursor ──────────────────────────────────────────────────────────
    def cursor(self, *args, **kwargs):
        import psycopg2.extras  # type: ignore
        kwargs.setdefault("cursor_factory", psycopg2.extras.DictCursor)
        return self._conn.cursor(*args, **kwargs)

    # ── Convenience execute (used by ai.py directly on db object) ───────
    def execute(self, sql: str, params=()):
        """Execute SQL with automatic ? → %s conversion. Returns cursor."""
        import psycopg2.extras  # type: ignore
        pg_sql = sql.replace("?", "%s")
        pg_sql = re.sub(r"\s+COLLATE\s+NOCASE\b", "", pg_sql, flags=re.IGNORECASE)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(pg_sql, list(params) if params else [])
        return cur

    # ── Transaction control ─────────────────────────────────────────────
    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    # ── Connection lifecycle ─────────────────────────────────────────────
    def close(self):
        """Return connection to the pool."""
        try:
            import psycopg2.extensions
            if self._conn.info.transaction_status != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                self._conn.rollback()

            if self._conn.closed != 0:
                self._pool.putconn(self._conn, close=True)
            else:
                self._pool.putconn(self._conn)
        except Exception as exc:
            logger.warning("Error returning PG connection to pool: %s", exc)
            try:
                self._pool.putconn(self._conn, close=True)
            except Exception:
                pass


# ============================================================
# DATABASE CONNECTION — unified entry point
# ============================================================

def get_db():
    """
    Return a database connection for the current environment.

    * PostgreSQL: a pooled psycopg2 connection (_PooledPgConn wrapper).
    * SQLite:     a sqlite3.Connection with row_factory and WAL mode.

    Both return objects expose .cursor(), .commit(), .rollback(), .close().
    Routes use db_compat.execute() to adapt SQL placeholders automatically.
    """
    if _pg_pool is not None:
        conn = _pg_pool.getconn()
        return _PooledPgConn(_pg_pool, conn)

    # ── SQLite (local development) ───────────────────────────────────────
    # Reject SQLite in production — must use PostgreSQL
    _prod_val = os.environ.get("PRODUCTION", "false").lower()
    if (
        _prod_val in ("true", "1", "yes", "y", "t")
        or os.environ.get("RENDER")
    ):
        raise RuntimeError(
            "Production environment detected but no PostgreSQL connection pool "
            "is configured. Set DATABASE_URL=postgresql://... to use PostgreSQL."
        )
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,
        timeout=30.0,
    )
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


# ============================================================
# PROJECT PATHS  (SQLite only; preserved for local dev)
# ============================================================

def _resolve_paths():
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

    for parent in Path(__file__).resolve().parents:
        db_cand = parent / "database" / "civicpulse.db"
        schema_cand = parent / "database" / "schema.sql"
        if schema_cand.exists() or db_cand.exists():
            return parent / "database", db_cand, schema_cand

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
# POSTGRES EXTENSION INITIALIZATION
# ============================================================

def _init_postgres_extensions() -> dict:
    """
    Attempt to create ``postgis`` and ``vector`` extensions.
    Each is tried independently; failure is logged as a warning (not fatal).

    Returns a dict of {ext_name: bool} indicating what was available.
    """
    available = {"postgis": False, "vector": False}
    if _pg_engine is None:
        return available

    for ext in ("postgis", "vector"):
        try:
            with _pg_engine.begin() as conn:
                conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext};"))
            available[ext] = True
            logger.info("PostgreSQL extension '%s' is available.", ext)
        except Exception as exc:
            logger.warning(
                "PostgreSQL extension '%s' is not available: %s  "
                "Related features will operate in degraded mode.",
                ext, exc,
            )
    return available


# ============================================================
# POSTGRES SCHEMA INITIALIZATION
# ============================================================

def _find_pg_schema() -> Optional[Path]:
    for parent in Path(__file__).resolve().parents:
        cand = parent / "database" / "postgres_schema.sql"
        if cand.exists():
            return cand
    return None


def _init_postgres():
    """
    Apply ``database/postgres_schema.sql`` to the configured PostgreSQL
    database.  The schema uses ``IF NOT EXISTS`` throughout and DO $$ blocks
    for PostGIS-dependent DDL, so this is safe to run on an existing DB.
    """
    ext_available = _init_postgres_extensions()

    pg_schema_path = _find_pg_schema()
    if pg_schema_path is None:
        raise FileNotFoundError(
            "database/postgres_schema.sql not found.  Cannot initialise "
            "the PostgreSQL schema."
        )

    schema_sql = pg_schema_path.read_text(encoding="utf-8")

    if _pg_engine is not None:
        try:
            with _pg_engine.begin() as conn:
                conn.execute(text(schema_sql))
            logger.info(
                "PostgreSQL schema applied from %s  (postgis=%s, vector=%s)",
                pg_schema_path,
                ext_available["postgis"],
                ext_available["vector"],
            )
            return
        except Exception as exc:
            logger.error(
                "Failed to apply PostgreSQL schema via SQLAlchemy: %s", exc
            )
            raise

    # Fallback: use psycopg2 pool directly
    conn = _pg_pool.getconn()
    try:
        old_autocommit = conn.autocommit
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(schema_sql)
        conn.autocommit = old_autocommit
    finally:
        _pg_pool.putconn(conn)

    logger.info("PostgreSQL schema applied (via psycopg2 pool).")


# ============================================================
# DATABASE INITIALIZATION — unified entry point
# ============================================================

def initialize_database():
    """
    Run all required database initialization steps.

    * PostgreSQL → apply postgres_schema.sql (idempotent).
    * SQLite     → run schema.sql + all incremental migration helpers.
    """
    if _pg_pool is not None:
        _init_postgres()
        return

    # SQLite path — all existing helpers preserved and called in order
    _init_sqlite()


def _init_sqlite():
    """Initialize SQLite database using the existing schema + helpers."""
    init_db()
    init_users_table()
    add_status_column()
    add_location_columns()
    init_votes_table()
    init_evidence_table()
    init_participatory_priority_table()
    add_ai_columns_to_complaints()
    init_ai_analyses_table()


# ============================================================
# SQLITE-ONLY HELPERS  (preserved unchanged for local dev / tests)
# ============================================================

def init_db():
    """Create the base database structure from schema.sql."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Database schema not found: {SCHEMA_PATH}"
        )
    db = get_db()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as file:
            schema = file.read()
        db.executescript(schema)
        db.commit()
    finally:
        db.close()


def add_status_column():
    """Add complaint status column if it does not already exist."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("PRAGMA table_info(complaints)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "status" not in columns:
            cursor.execute(
                "ALTER TABLE complaints ADD COLUMN status TEXT DEFAULT 'Pending'"
            )
            db.commit()
    finally:
        db.close()


def init_votes_table():
    """Create complaint voting table if it does not exist."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS complaint_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id INTEGER NOT NULL,
                voter_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (complaint_id, voter_id),
                FOREIGN KEY (complaint_id)
                    REFERENCES complaints(id) ON DELETE CASCADE
            )
            """
        )
        db.commit()
    finally:
        db.close()


def init_participatory_priority_table():
    """Create the participatory budgeting priority tables."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS participatory_priorities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                issue_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, issue_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (issue_id) REFERENCES complaints(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS participatory_priority_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id INTEGER NOT NULL,
                citizen_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (complaint_id, citizen_id),
                FOREIGN KEY (complaint_id)
                    REFERENCES complaints(id) ON DELETE CASCADE,
                FOREIGN KEY (citizen_id)
                    REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        db.commit()
    finally:
        db.close()


def init_evidence_table():
    """Create complaint evidence table if it does not exist."""
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
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (complaint_id)
                    REFERENCES complaints(id) ON DELETE CASCADE
            )
            """
        )
        db.commit()
    finally:
        db.close()


def init_users_table():
    """Create the users table if it does not exist."""
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


def add_location_columns():
    """Add geo-location columns to the complaints table if they don't exist."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("PRAGMA table_info(complaints)")
        columns = [row["name"] for row in cursor.fetchall()]
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
        for col_name, col_type in new_columns.items():
            if col_name not in columns:
                cursor.execute(
                    f"ALTER TABLE complaints ADD COLUMN {col_name} {col_type}"
                )
        db.commit()
    finally:
        db.close()


def add_ai_columns_to_complaints():
    """Add AI audit columns to the complaints table if they don't already exist."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("PRAGMA table_info(complaints)")
        columns = [row["name"] for row in cursor.fetchall()]
        ai_columns = {
            "user_selected_category": "TEXT",
            "category_source": "TEXT DEFAULT 'manual'",
            "ai_confidence": "REAL",
            "ai_analysis_id": "TEXT",
            "ai_needs_review": "INTEGER DEFAULT 0",
        }
        for col_name, col_type in ai_columns.items():
            if col_name not in columns:
                cursor.execute(
                    f"ALTER TABLE complaints ADD COLUMN {col_name} {col_type}"
                )
        db.commit()
    finally:
        db.close()


def init_ai_analyses_table():
    """Create the AI analysis audit table if it does not exist."""
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
                    REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        db.commit()
    finally:
        db.close()