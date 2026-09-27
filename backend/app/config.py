"""T07 — env config. Spec: docs/specs/S04-message-endpoint.md section 1.

Only ALLOWED_ORIGINS is required/enforced today. Other env vars (SUPABASE_*, GROQ_API_KEY,
GEMINI_API_KEY, SARVAM_API_KEY, LLM_PROVIDER) become required once the ticket that needs them
lands (T14, T12, T26) and get their own loader here at that point.
"""

import os


def get_allowed_origins() -> list[str]:
    """Comma-separated ALLOWED_ORIGINS -> trimmed, non-empty origins. Raises if none are set."""
    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if not origins:
        raise RuntimeError("ALLOWED_ORIGINS is not set")
    return origins
