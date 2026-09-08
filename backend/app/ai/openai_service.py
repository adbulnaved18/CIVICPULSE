# ============================================================
# CivicPulse AI — Service Layer (Backward Compatibility Shim)
# ============================================================
#
# Re-exports service functions from gemini_service.
# ============================================================

from backend.app.ai.gemini_service import transcribe_audio, analyze_report  # noqa: F401
