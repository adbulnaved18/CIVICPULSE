import os
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.app.auth.dependencies import COOKIE_NAME, get_current_user
from backend.app.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from backend.app.models.user import UserLogin, UserOut, UserSignup
from backend.app.services.database import get_db
from backend.app.services import db_compat

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {
        "1", "true", "yes", "on"
    }


COOKIE_SECURE = _env_bool("COOKIE_SECURE", False)
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax").strip().lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    COOKIE_SAMESITE = "lax"
# Per RFC 6265bis, SameSite=None requires Secure=True in modern browsers
if COOKIE_SAMESITE == "none":
    COOKIE_SECURE = True


# ============================================================
# SIGNUP
# ============================================================

@router.post("/signup", response_model=UserOut)
def signup(user: UserSignup):
    db = get_db()

    try:
        # Check email uniqueness
        cursor = db_compat.execute(
            db,
            "SELECT id FROM users WHERE email = ?",
            (user.email,),
        )

        if cursor.fetchone() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists",
            )

        password_hash = hash_password(user.password)

        _, new_id = db_compat.execute_insert(
            db,
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (?, ?, ?, 'citizen')
            """,
            (user.name, user.email, password_hash),
        )

        db.commit()

        return UserOut(
            id=new_id,
            name=user.name,
            email=user.email,
            role="citizen"
        )

    except HTTPException:
        db.rollback()
        raise

    finally:
        db.close()


# ============================================================
# LOGIN
# ============================================================

failed_login_attempts = {}

@router.post("/login", response_model=UserOut)
def login(credentials: UserLogin, response: Response):
    email = credentials.email
    now = time.time()

    if email in failed_login_attempts:
        lock_until = failed_login_attempts[email].get("lock_until")
        if lock_until and now > lock_until:
            del failed_login_attempts[email]
        elif lock_until and now <= lock_until:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts. Please wait 1 minute."
            )

    db = get_db()

    try:
        cursor = db_compat.execute(
            db,
            """
            SELECT id, name, email, password_hash, role
            FROM users
            WHERE email = ?
            """,
            (credentials.email,),
        )
        row = cursor.fetchone()

    finally:
        db.close()

    if row is None or not verify_password(
        credentials.password, row["password_hash"]
    ):
        if email not in failed_login_attempts:
            failed_login_attempts[email] = {"count": 0, "lock_until": None}

        failed_login_attempts[email]["count"] += 1

        if failed_login_attempts[email]["count"] >= 5:
            failed_login_attempts[email]["lock_until"] = time.time() + 60

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if email in failed_login_attempts:
        del failed_login_attempts[email]

    token = create_access_token({"sub": str(row["id"])})

    # httpOnly cookie: JS on the frontend can't read it, but the browser
    # sends it automatically on every request as long as fetch/axios
    # calls include credentials.
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        max_age=60 * 60 * 24,
        path="/",
    )

    return UserOut(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        role=row["role"],
        token=token,
    )


# ============================================================
# LOGOUT
# ============================================================

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        httponly=True,
    )
    return {"message": "Logged out successfully"}


# ============================================================
# CURRENT USER
# ============================================================

@router.get("/me", response_model=UserOut)
def get_me(current_user: dict = Depends(get_current_user)):
    return UserOut(**current_user)
