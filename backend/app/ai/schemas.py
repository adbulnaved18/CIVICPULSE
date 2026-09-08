# ============================================================
# CivicPulse AI — Pydantic Schemas
# ============================================================

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# CATEGORY ENUM
# ============================================================

# Exactly the 12 categories already used in the frontend.
CIVIC_CATEGORIES = Literal[
    "Drainage & Waterlogging",
    "Environment",
    "Footpaths & Pedestrian Safety",
    "Parks & Public Spaces",
    "Public Health & Hygiene",
    "Public Infrastructure",
    "Roads & Potholes",
    "Sanitation & Waste",
    "Stray Animals",
    "Streetlights & Electricity",
    "Traffic & Transportation",
    "Water Supply",
]

CIVIC_CATEGORY_LIST = [
    "Drainage & Waterlogging",
    "Environment",
    "Footpaths & Pedestrian Safety",
    "Parks & Public Spaces",
    "Public Health & Hygiene",
    "Public Infrastructure",
    "Roads & Potholes",
    "Sanitation & Waste",
    "Stray Animals",
    "Streetlights & Electricity",
    "Traffic & Transportation",
    "Water Supply",
]


# ============================================================
# STRUCTURED OUTPUT — what the model MUST return
# ============================================================

class ReportAnalysis(BaseModel):
    """
    Structured output from the AI classifier.
    The model cannot return a value outside the enum.
    """

    suggested_category: CIVIC_CATEGORIES = Field(
        description="Exactly one of the 12 CivicPulse categories."
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Classifier confidence between 0 and 1.",
    )

    needs_review: bool = Field(
        description="True when the model is uncertain and a human should verify."
    )

    detected_language: Literal["en", "hi", "unknown"] = Field(
        description="Language detected in the description text."
    )

    short_reason: str = Field(
        max_length=300,
        description=(
            "One or two sentences explaining the category choice. "
            "Do not include personal or sensitive details."
        ),
    )

    text_image_consistent: Optional[bool] = Field(
        default=None,
        description=(
            "True when text and image point to the same issue. "
            "None when only one input was provided."
        ),
    )

    alternative_category: Optional[CIVIC_CATEGORIES] = Field(
        default=None,
        description="Second-best category when confidence is not high.",
    )


# ============================================================
# TRANSCRIPTION RESPONSE
# ============================================================

class TranscribeResponse(BaseModel):
    """Response from POST /ai/transcribe."""

    transcript: str
    detected_language: str
    model: str


# ============================================================
# ANALYSIS RESPONSE  (what the API endpoint returns)
# ============================================================

class AnalyzeResponse(BaseModel):
    """Response from POST /ai/analyze-report."""

    analysis_id: str
    suggested_category: str
    confidence: float
    needs_review: bool
    detected_language: str
    short_reason: str
    text_image_consistent: Optional[bool] = None
    alternative_category: Optional[str] = None


# ============================================================
# AI HEALTH RESPONSE
# ============================================================

class AIHealthResponse(BaseModel):
    """Response from GET /ai/health."""

    ai_available: bool
    message: str
