"""
Run this once from the project root (same place you run `uvicorn` from)
to create an admin account, or promote an existing citizen account to
admin.

Usage:
    python seed_admin.py

It will prompt for name, email, and password if the account doesn't exist
yet, or just promote the account to admin if that email is already
registered (e.g. if you signed up normally through the app first).
"""

import getpass
import os
import sys
from pathlib import Path

# Load .env before any app imports so DATABASE_URL etc. are available
try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parent
    load_dotenv(_root / ".env")
except ImportError:
    pass

from backend.app.auth.security import hash_password
from backend.app.services.database import get_db, initialize_database
from backend.app.services import db_compat


def main():
    # Make sure all tables exist even if this is run before the API
    # has ever started.
    initialize_database()

    email = (os.environ.get("ADMIN_EMAIL") or "").strip()
    if not email:
        email = input("Admin email: ").strip()

    if not email:
        print("Admin email cannot be empty. Aborting.")
        sys.exit(1)

    db = get_db()

    try:
        cursor = db_compat.execute(
            db, "SELECT id, role FROM users WHERE email = ?", (email,)
        )
        existing = cursor.fetchone()

        if existing is not None:
            db_compat.execute(
                db, "UPDATE users SET role = 'admin' WHERE email = ?", (email,)
            )
            db.commit()
            print(
                f"'{email}' already existed and has been promoted to admin."
            )
            return

        name = (os.environ.get("ADMIN_NAME") or "").strip()
        if not name:
            name = input("Admin name: ").strip() or "Administrator"

        password = (os.environ.get("ADMIN_PASSWORD") or "").strip()
        if not password:
            password = getpass.getpass("Admin password: ")
            confirm = getpass.getpass("Confirm password: ")

            if password != confirm:
                print("Passwords did not match. Aborting.")
                sys.exit(1)

        password_hash = hash_password(password)

        db_compat.execute_insert(
            db,
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (?, ?, ?, 'admin')
            """,
            (name, email, password_hash),
        )
        db.commit()

        print(f"Admin account '{email}' created successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
