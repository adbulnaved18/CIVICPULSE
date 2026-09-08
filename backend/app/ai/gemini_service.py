# ============================================================
# CivicPulse AI — Google Gemini Service Layer
# ============================================================
#
# All provider calls originate here.
# This module is imported ONLY by backend code (routes/ai.py).
# The GEMINI_API_KEY never reaches the React frontend.
# ============================================================

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from backend.app.ai.config import (
    get_gemini_api_key,
    GEMINI_MODEL,
    GEMINI_FALLBACK_MODEL,
    GEMINI_STT_MODEL,
    AI_AUTO_ACCEPT_THRESHOLD,
)
from backend.app.ai.schemas import ReportAnalysis
from backend.app.ai.prompts import CLASSIFIER_SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)


def _get_client() -> genai.Client:
    """Return a Google GenAI client using the server-side API key."""
    if genai is None or types is None:
        raise RuntimeError(
            "Google GenAI SDK is not installed. Run: pip install -r backend/requirements.txt"
        )
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    return genai.Client(api_key=api_key)


def is_provider_sdk_available() -> bool:
    """Return whether the Google GenAI SDK imported successfully."""
    return genai is not None and types is not None


def _public_provider_error(exc: Exception, operation: str) -> str:
    """Convert provider failures into useful messages without exposing secrets."""
    code = getattr(exc, "code", None)
    status_name = str(getattr(exc, "status", "")).upper()
    message = str(exc).lower()

    if code in (401, 403) or "api key not valid" in message or "permission_denied" in message:
        return (
            "Gemini rejected the API key. Create/verify the key in Google AI Studio "
            "and set GEMINI_API_KEY on the backend server."
        )
    if code == 429 or "resource_exhausted" in message or "quota" in message:
        return "Gemini quota or rate limit was reached. Check the API key's quota and billing limits."
    if code == 404 or "not_found" in status_name or "model" in message and "not found" in message:
        return "The configured Gemini model is unavailable. Check GEMINI_MODEL and GEMINI_STT_MODEL."
    if code == 400 or "invalid_argument" in status_name:
        return f"Gemini rejected the {operation} request. Check the uploaded file and model settings."
    if "timeout" in message or "connection" in message or "network" in message:
        return "Could not connect to Gemini. Check the backend server's internet connection."
    return f"Gemini {operation} failed. Check the backend log for the provider error."


# ============================================================
# TRANSCRIPTION
# ============================================================

async def transcribe_audio(
    file_bytes: bytes,
    filename: str,
    language_hint: Optional[str] = None,
) -> dict:
    """
    Transcribe an audio clip using Google Gemini multimodal audio capabilities.

    Returns:
        {"transcript": str, "detected_language": str, "model": str}

    Raises:
        ValueError  — invalid input
        RuntimeError — provider error
    """

    if not file_bytes:
        raise ValueError("Audio file is empty.")

    # Determine audio mime type from filename or default to audio/webm
    mime_type = "audio/webm"
    lower_fn = filename.lower()
    if lower_fn.endswith(".wav"):
        mime_type = "audio/wav"
    elif lower_fn.endswith(".mp3"):
        mime_type = "audio/mp3"
    elif lower_fn.endswith(".m4a") or lower_fn.endswith(".mp4"):
        mime_type = "audio/mp4"
    elif lower_fn.endswith(".ogg"):
        mime_type = "audio/ogg"
    elif lower_fn.endswith(".flac"):
        mime_type = "audio/flac"

    prompt_text = (
        "Please listen to this audio recording and transcribe it accurately into text. "
        "Return ONLY a JSON object formatted exactly as: "
        '{"transcript": "the full transcription text", "detected_language": "en" | "hi" | "unknown"}. '
        "Do not include markdown blocks or any other explanation."
    )

    if language_hint:
        prompt_text += f" Language hint: {language_hint}."

    def _sync_call():
        client = _get_client()
        part = types.Part.from_bytes(
            data=file_bytes,
            mime_type=mime_type,
        )
        response = client.models.generate_content(
            model=GEMINI_STT_MODEL,
            contents=[part, prompt_text],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        return response.text

    try:
        raw_text = await asyncio.to_thread(_sync_call)
        cleaned_json = raw_text.strip()
        if cleaned_json.startswith("```json"):
            cleaned_json = cleaned_json[7:]
        if cleaned_json.startswith("```"):
            cleaned_json = cleaned_json[3:]
        if cleaned_json.endswith("```"):
            cleaned_json = cleaned_json[:-3]
        cleaned_json = cleaned_json.strip()

        data = json.loads(cleaned_json)
        transcript = data.get("transcript", "").strip()
        detected_language = data.get("detected_language", language_hint or "unknown")

        return {
            "transcript": transcript,
            "detected_language": detected_language,
            "model": GEMINI_STT_MODEL,
        }

    except Exception as exc:
        logger.exception("Gemini transcription error")
        raise RuntimeError(_public_provider_error(exc, "transcription")) from exc


# ============================================================
# REPORT ANALYSIS
# ============================================================

async def analyze_report(
    description: Optional[str],
    image_bytes: Optional[bytes],
    image_mime: Optional[str],
    selected_category: Optional[str] = None,
    use_fallback: bool = False,
) -> ReportAnalysis:
    """
    Classify a civic complaint using Gemini multimodal capabilities.

    At least one of description or image_bytes must be provided.

    Returns a validated ReportAnalysis object.

    Raises:
        ValueError  — missing input
        RuntimeError — provider error
    """

    if not description and not image_bytes:
        raise ValueError("At least one of description or image is required.")

    model = GEMINI_FALLBACK_MODEL if use_fallback else GEMINI_MODEL
    user_text = build_user_message(description, selected_category)

    contents: list = []

    if image_bytes and image_mime:
        contents.append(
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=image_mime,
            )
        )

    contents.append(user_text)

    def _sync_call():
        client = _get_client()
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=CLASSIFIER_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ReportAnalysis,
                temperature=0.0,
                max_output_tokens=500,
            ),
        )
        return response.text

    try:
        raw_text = await asyncio.to_thread(_sync_call)
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        analysis = ReportAnalysis.model_validate(data)

        # --------------------------------------------------------
        # Low-confidence fallback: retry once with fallback model
        # --------------------------------------------------------
        if (
            not use_fallback
            and analysis.confidence < AI_AUTO_ACCEPT_THRESHOLD
            and GEMINI_FALLBACK_MODEL != GEMINI_MODEL
        ):
            try:
                analysis = await analyze_report(
                    description=description,
                    image_bytes=image_bytes,
                    image_mime=image_mime,
                    selected_category=selected_category,
                    use_fallback=True,
                )
            except Exception:
                pass

        return analysis

    except Exception as exc:
        logger.exception("Gemini analysis error (model=%s)", model)
        raise RuntimeError(_public_provider_error(exc, "analysis")) from exc
