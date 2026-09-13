import os
import sys
from pathlib import Path

# ============================================================
# PATH SETUP
# ============================================================
# Ensure project root, backend, and app directories are in sys.path
_FILE_PATH = Path(__file__).resolve()
_APP_DIR = _FILE_PATH.parent
_BACKEND_DIR = _APP_DIR.parent
_PROJECT_ROOT = _BACKEND_DIR.parent

for _path in (str(_PROJECT_ROOT), str(_BACKEND_DIR), str(_APP_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Ensure 'backend' module is always importable even if deployed from backend/ root
import types
if "backend" not in sys.modules:
    try:
        import backend  # noqa: F401
    except ImportError:
        _backend_pkg = types.ModuleType("backend")
        _backend_pkg.__path__ = [str(_BACKEND_DIR)]
        sys.modules["backend"] = _backend_pkg

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
    load_dotenv(_BACKEND_DIR / ".env")
except ImportError:
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import urlparse

# ============================================================
# CONFIGURATION VALIDATION (before any database/route imports)
# ============================================================
def is_production() -> bool:
    val = os.environ.get("PRODUCTION", "false").lower()
    if val in ("true", "1", "yes", "y", "t"):
        return True
    if os.environ.get("RENDER"):
        return True
    return False

# Normalize postgres:// → postgresql:// in the environment so every
# downstream module (database.py, migration scripts) sees a consistent URL.
_raw_db_url = os.environ.get("DATABASE_URL", "")
if _raw_db_url.startswith("postgres://"):
    os.environ["DATABASE_URL"] = "postgresql://" + _raw_db_url[len("postgres://"):]


def validate_startup_config():
    """
    Validate production configuration (DATABASE_URL, Supabase credentials, and SECRET_KEY).
    Raises RuntimeError if any required production setting is invalid or insecure.
    """
    if not is_production():
        return

    db_url = os.environ.get("DATABASE_URL", "")
    if not (db_url.startswith("postgresql://") or db_url.startswith("postgres://")):
        raise RuntimeError("Production requires PostgreSQL. DATABASE_URL must start with postgresql:// or postgres://")

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY") or not os.environ.get("SUPABASE_STORAGE_BUCKET"):
        raise RuntimeError("Production requires SUPABASE_URL, SUPABASE_SERVICE_KEY, and SUPABASE_STORAGE_BUCKET.")

    # Validate SECRET_KEY
    secret_key = os.environ.get("SECRET_KEY", "")
    if not secret_key:
        try:
            from backend.app.auth.security import SECRET_KEY as _sec
            secret_key = _sec
        except ImportError:
            try:
                from app.auth.security import SECRET_KEY as _sec
                secret_key = _sec
            except ImportError:
                secret_key = ""

    if secret_key in ("dev-only-secret-change-me-before-deployment", "change-this-to-a-secure-random-string-in-production", ""):
        raise RuntimeError("Insecure SECRET_KEY in production. Set a strong SECRET_KEY environment variable.")


if is_production():
    validate_startup_config()


# Import routes and database initializer with fallbacks
try:
    from backend.app.routes.complaints import router as complaints_router
    from backend.app.routes.participatory_budgeting import (
        router as participatory_budgeting_router,
    )
    from backend.app.routes.auth import router as auth_router
    from backend.app.routes.ai import router as ai_router
    from backend.app.services.database import initialize_database
    from backend.app.services.storage import is_storage_configured
except ImportError:
    from app.routes.complaints import router as complaints_router
    from app.routes.participatory_budgeting import (
        router as participatory_budgeting_router,
    )
    from app.routes.auth import router as auth_router
    from app.routes.ai import router as ai_router
    from app.services.database import initialize_database
    from app.services.storage import is_storage_configured


# ============================================================
# DIRECTORIES
# ============================================================
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "uploads")).resolve()
(UPLOAD_DIR / "evidence").mkdir(parents=True, exist_ok=True)



# ============================================================
# FASTAPI APPLICATION
# ============================================================
app = FastAPI(
    title="CivicPulse API",
    description="CivicPulse civic complaint, community support and participatory budgeting API",
    version="1.0.0",
)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================
initialize_database()


# ============================================================
# CORS & CSRF
# ============================================================
cors_origins_env = os.environ.get("CORS_ORIGINS", "")
allowed_origins = [
    "https://civicpulse-seven-beta.vercel.app"
]

if not is_production():
    allowed_origins.extend([
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ])

if cors_origins_env:
    for origin in cors_origins_env.split(","):
        clean_origin = origin.strip()
        if clean_origin and clean_origin not in allowed_origins:
            allowed_origins.append(clean_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if "access_token" in request.cookies:
                origin = request.headers.get("origin") or request.headers.get("referer")
                if origin:
                    parsed_origin = f"{urlparse(origin).scheme}://{urlparse(origin).netloc}"
                    if parsed_origin not in allowed_origins:
                        return JSONResponse(status_code=403, content={"message": "CSRF check failed: invalid origin."})
                else:
                    return JSONResponse(status_code=403, content={"message": "CSRF check failed: missing origin."})
        return await call_next(request)

app.add_middleware(CSRFMiddleware)


# ============================================================
# STATIC FILES
# ============================================================
# Uploaded evidence/photos are served through /uploads only in
# local development.  In production, Supabase Storage handles
# serving via signed URLs generated by the backend at read time.
if not is_storage_configured():
    (UPLOAD_DIR / "evidence").mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
else:
    # Still create the dir as a safety guard (harmless in production)
    (UPLOAD_DIR / "evidence").mkdir(parents=True, exist_ok=True)


# ============================================================
# API ROUTES
# ============================================================
# Civic complaints
app.include_router(complaints_router)

# Participatory Budgeting
app.include_router(participatory_budgeting_router)

# Auth
app.include_router(auth_router)

# AI (transcription + category classification)
app.include_router(ai_router)


# ============================================================
# ROOT & HEALTH ENDPOINTS
# ============================================================
@app.get("/")
def root():
    return {
        "message": "CivicPulse API is running",
        "status": "ok",
        "services": {
            "complaints": "/complaints/",
            "participatory_budgeting": "/participatory-budgeting/health",
            "uploads": "/uploads/",
            "ai": "/ai/health",
        },
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "CivicPulse API",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )
