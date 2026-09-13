from fastapi import Depends, HTTPException, Request, status

from backend.app.auth.security import decode_access_token
from backend.app.services.database import get_db
from backend.app.services import db_compat

COOKIE_NAME = "access_token"


def get_current_user(request: Request) -> dict:
    """
    Reads the JWT from the httpOnly cookie, validates it, and loads the
    corresponding user from the database. Raises 401 if not authenticated.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    user_id = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    db = get_db()

    try:
        cursor = db_compat.execute(
            db,
            "SELECT id, name, email, role FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()

    finally:
        db.close()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )

    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
    }


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Route dependency that restricts an endpoint to admins only.
    """
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user
