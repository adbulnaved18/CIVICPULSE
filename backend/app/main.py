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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import routes and database initializer with fallbacks
try:
    from backend.app.routes.complaints import router as complaints_router
    from backend.app.routes.participatory_budgeting import (
        router as participatory_budgeting_router,
    )
    from backend.app.routes.auth import router as auth_router
    from backend.app.routes.ai import router as ai_router
    from backend.app.services.database import initialize_database
except ImportError:
    from app.routes.complaints import router as complaints_router
    from app.routes.participatory_budgeting import (
        router as participatory_budgeting_router,
    )
    from app.routes.auth import router as auth_router
    from app.routes.ai import router as ai_router
    from app.services.database import initialize_database


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
# CORS
# ============================================================
cors_origins_env = os.environ.get("CORS_ORIGINS", "")
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
if cors_origins_env:
    for origin in cors_origins_env.split(","):
        clean_origin = origin.strip()
        if clean_origin and clean_origin not in allowed_origins:
            allowed_origins.append(clean_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# STATIC FILES
# ============================================================
# Uploaded evidence/photos will be accessible through:
# http://127.0.0.1:8000/uploads/...
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


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
