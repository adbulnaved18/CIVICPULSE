"""
CivicPulse — Database Compatibility Adapter
============================================
Bridges SQLite (local development) and psycopg2 / PostgreSQL (production).

All route code continues to write SQL with SQLite-style ``?`` placeholders.
This module converts them to ``%s`` (psycopg2 style) transparently, and
handles the small set of places where the two drivers diverge:

  * Placeholder style  (? vs %s)
  * COLLATE NOCASE     (SQLite only; stripped for PostgreSQL)
  * lastrowid          (SQLite cursor attr vs RETURNING id)
  * UniqueViolation    (sqlite3.IntegrityError vs psycopg2.errors.*)

Nothing in this module changes business logic, SQL semantics, or
response formats.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Optional, Tuple


# ============================================================
# DB-TYPE DETECTION
# ============================================================

def is_sqlite(db) -> bool:
    """
    Return True when *db* is a SQLite connection (or our pooled PG wrapper
    pretending to be one — it never is, so this stays simple).
    """
    return isinstance(db, sqlite3.Connection)


# ============================================================
# SQL TRANSLATION
# ============================================================

def _to_pg(sql: str) -> str:
    """
    Convert a SQLite SQL string to PostgreSQL compatible SQL:
      - Replace ``?`` parameter markers with ``%s``.
      - Drop ``COLLATE NOCASE`` clauses (PostgreSQL ignores them; use LOWER()
        where case-insensitive ordering is truly needed — already done in most
        queries in this codebase).
    """
    result = []
    i = 0
    n = len(sql)
    while i < n:
        if sql[i] == "'":
            result.append("'")
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i+1] == "'":
                        result.append("''")
                        i += 2
                    else:
                        result.append("'")
                        i += 1
                        break
                else:
                    result.append(sql[i])
                    i += 1
        elif sql[i:i+2] == "--":
            result.append("--")
            i += 2
            while i < n and sql[i] != '\n':
                result.append(sql[i])
                i += 1
        elif sql[i:i+2] == "/*":
            result.append("/*")
            i += 2
            while i < n:
                if sql[i:i+2] == "*/":
                    result.append("*/")
                    i += 2
                    break
                else:
                    result.append(sql[i])
                    i += 1
        elif sql[i] == "?":
            result.append("%s")
            i += 1
        else:
            result.append(sql[i])
            i += 1
            
    sql = "".join(result)
    sql = re.sub(r"\s+COLLATE\s+NOCASE\b", "", sql, flags=re.IGNORECASE)
    return sql


# ============================================================
# EXECUTE HELPERS
# ============================================================

def execute(db, sql: str, params=()):
    """
    Execute *sql* with *params* on *db*, adapting placeholder style.

    Returns the cursor so callers can call ``.fetchone()`` / ``.fetchall()``
    as normal.

    Usage (replaces ``cursor.execute(sql, params)`` in routes)::

        cursor = db_compat.execute(db, "SELECT id FROM users WHERE id = ?", (uid,))
        row = cursor.fetchone()
    """
    cursor = db.cursor()
    if is_sqlite(db):
        cursor.execute(sql, params)
    else:
        cursor.execute(_to_pg(sql), list(params) if params else [])
    return cursor


def execute_insert(
    db,
    sql: str,
    params=(),
    id_col: str = "id",
) -> Tuple[Any, Optional[int]]:
    """
    Execute an INSERT statement and return ``(cursor, new_id)``.

    * SQLite  — uses ``cursor.lastrowid``.
    * PostgreSQL — automatically appends ``RETURNING {id_col}`` and reads
      the result. The caller's SQL must *not* already contain a RETURNING
      clause.

    Usage::

        cursor, new_id = db_compat.execute_insert(
            db,
            "INSERT INTO users (name, email) VALUES (?, ?)",
            (name, email),
        )
    """
    if is_sqlite(db):
        cursor = db.cursor()
        cursor.execute(sql, params)
        return cursor, cursor.lastrowid

    # PostgreSQL path
    stripped = sql.rstrip().rstrip(";")
    pg_sql = _to_pg(stripped) + f" RETURNING {id_col}"
    cursor = db.cursor()
    cursor.execute(pg_sql, list(params) if params else [])
    row = cursor.fetchone()
    if row is None:
        return cursor, None
    # DictCursor → row[id_col]; tuple cursor → row[0]
    try:
        new_id = row[id_col]
    except (TypeError, KeyError):
        new_id = row[0]
    return cursor, int(new_id)


# ============================================================
# UNIQUE / DUPLICATE-KEY VIOLATION
# ============================================================

def is_unique_violation(exc: Exception) -> bool:
    """
    Return True when *exc* represents a unique / duplicate-key constraint
    violation, regardless of whether we are using SQLite or psycopg2.

    Usage (replaces the SQLite-specific check in the vote handler)::

        except Exception as err:
            if db_compat.is_unique_violation(err):
                return {"message": "Already voted"}
            raise
    """
    # SQLite
    if isinstance(exc, sqlite3.IntegrityError):
        return "UNIQUE constraint failed" in str(exc) or "unique" in str(exc).lower()

    # SQLAlchemy
    try:
        import sqlalchemy.exc
        if isinstance(exc, sqlalchemy.exc.IntegrityError):
            orig_msg = str(exc.orig).lower() if hasattr(exc, "orig") else str(exc).lower()
            return "unique" in orig_msg or "duplicate key" in orig_msg
    except ImportError:
        pass

    # psycopg2 — import lazily so the module loads even without the driver
    try:
        import psycopg2.errors as _pg_errors  # type: ignore
        if isinstance(exc, _pg_errors.UniqueViolation):
            return True
    except (ImportError, AttributeError):
        pass

    # Generic fallback (covers other psycopg2 IntegrityError subtypes)
    msg = str(exc).lower()
    return "unique" in msg or "duplicate key" in msg
