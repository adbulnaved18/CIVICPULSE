"""
CivicPulse — LLM Duplicate Verifier
===================================
Uses Gemini to resolve ambiguous duplicate cases.
"""

import json
import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)

def verify_duplicate_pair(new_complaint: Dict, existing_complaint: Dict) -> Dict:
    """
    Call Gemini to determine if two complaints describe the exact same real-world incident.
    Returns: {"same_incident": bool, "confidence": float, "reasoning": str}
    """
    try:
        from backend.app.ai.config import get_gemini_api_key, GEMINI_MODEL
        from google import genai
        from google.genai import types

        api_key = get_gemini_api_key()
        if not api_key:
            return {"same_incident": False, "reasoning": "No API key"}

        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        You are a civic issue duplicate detector. Determine if these two complaints refer to the EXACT SAME physical incident.
        
        COMPLAINT A (New):
        Category: {new_complaint.get('category')}
        Location: {new_complaint.get('location')}
        Description: {new_complaint.get('description')}
        
        COMPLAINT B (Existing):
        Category: {existing_complaint.get('category')}
        Location: {existing_complaint.get('location')}
        Description: {existing_complaint.get('description')}
        
        Return JSON ONLY with this schema:
        {{"same_incident": boolean, "confidence": float between 0 and 1, "reasoning": "short explanation"}}
        """

        response = client.models.generate_content(
            model=GEMINI_MODEL or "gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3]
        
        return json.loads(text)

    except ImportError:
        logger.warning("google-genai SDK not installed — verification skipped.")
        return {"same_incident": False, "reasoning": "Missing SDK"}
    except Exception as exc:
        logger.warning("LLM duplicate verification failed: %s", exc)
        return {"same_incident": False, "reasoning": str(exc)}
