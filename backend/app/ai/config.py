# ============================================================
# CivicPulse AI — Configuration
# ============================================================
#
# Reads server-side environment variables only.
# NEVER import or reference anything from the React frontend.
#
# Required environment variable:
#   GEMINI_API_KEY   — your Google Gemini project key
#
# Optional (defaults shown):
#   GEMINI_MODEL                 gemini-2.5-flash
#   GEMINI_FALLBACK_MODEL        gemini-2.5-flash-lite
#   GEMINI_STT_MODEL             gemini-2.5-flash
#   AI_AUTO_ACCEPT_THRESHOLD     0.80
#   AI_REVIEW_THRESHOLD          0.60
#   AI_MAX_IMAGE_BYTES           5242880  (5 MB)
#   AI_MAX_AUDIO_BYTES           10485760 (10 MB)
# ============================================================

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # The health endpoint reports this clearly at runtime.
    load_dotenv = None

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = _PROJECT_ROOT / "backend"


def _load_environment() -> None:
    """Load local development environment files without replacing real env vars."""
    if load_dotenv is None:
        return
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
    load_dotenv(_BACKEND_DIR / ".env", override=False)


_load_environment()


# ============================================================
# API KEY
# ============================================================

# Leave blank here — set in your server environment or .env file.
# DO NOT hard-code a key in this file.
def get_gemini_api_key() -> str:
    # Re-read local files so a development-server restart sees recent changes.
    # Existing deployment environment variables always take precedence.
    _load_environment()
    return (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )

GEMINI_API_KEY = get_gemini_api_key()

# ============================================================
# MODEL NAMES
# ============================================================

# Primary multimodal model for category classification and vision.
GEMINI_MODEL: str = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

GEMINI_FALLBACK_MODEL: str = os.environ.get(
    "GEMINI_FALLBACK_MODEL",
    "gemini-3.5-flash-lite",
)

GEMINI_STT_MODEL: str = os.environ.get(
    "GEMINI_STT_MODEL",
    "gemini-3.5-flash-lite",
)

# ============================================================
# CONFIDENCE THRESHOLDS
# ============================================================

# >= this value  → auto-fill AI category; user can still correct
AI_AUTO_ACCEPT_THRESHOLD: float = float(
    os.environ.get("AI_AUTO_ACCEPT_THRESHOLD", "0.80")
)

# between this and AUTO_ACCEPT → show suggestion, ask to confirm
AI_REVIEW_THRESHOLD: float = float(
    os.environ.get("AI_REVIEW_THRESHOLD", "0.60")
)


# ============================================================
# FILE SIZE LIMITS
# ============================================================

# Maximum image upload size sent to the AI provider (bytes).
AI_MAX_IMAGE_BYTES: int = int(
    os.environ.get("AI_MAX_IMAGE_BYTES", str(5 * 1024 * 1024))
)

# Maximum audio clip size (bytes).
AI_MAX_AUDIO_BYTES: int = int(
    os.environ.get("AI_MAX_AUDIO_BYTES", str(10 * 1024 * 1024))
)

# Maximum audio duration (seconds) accepted by this application.
AI_MAX_AUDIO_SECONDS: int = int(
    os.environ.get("AI_MAX_AUDIO_SECONDS", "90")
)


# ============================================================
# ALLOWED MIME TYPES
# ============================================================

ALLOWED_AUDIO_MIME_TYPES: set = {
    "audio/webm",
    "audio/webm;codecs=opus",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mp3",
    "audio/mpeg",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/ogg",
    "audio/ogg;codecs=opus",
    "audio/flac",
}

ALLOWED_IMAGE_MIME_TYPES: set = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
}


# ============================================================
# HELPER
# ============================================================

def is_ai_available() -> bool:
    """Return True when the Gemini API key is configured."""
    key = get_gemini_api_key()
    return bool(key and key.strip())
