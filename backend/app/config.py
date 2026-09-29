"""T07/T12/T14 — env config. Spec: docs/specs/S04-message-endpoint.md section 1,
S05-turn-engine.md, S06-session-manager.md.

ALLOWED_ORIGINS, the LLM vars (GROQ_API_KEY, GEMINI_API_KEY, GROQ_MODEL, GEMINI_MODEL,
LLM_PROVIDER), and the Supabase vars (SUPABASE_URL, SUPABASE_SERVICE_KEY) are enforced here.
SARVAM_API_KEY becomes required once the ticket that needs it lands (T26) and gets its own loader
here at that point.
"""

import os
from dataclasses import dataclass
from typing import Literal


def get_allowed_origins() -> list[str]:
    """Comma-separated ALLOWED_ORIGINS -> trimmed, non-empty origins. Raises if none are set."""
    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if not origins:
        raise RuntimeError("ALLOWED_ORIGINS is not set")
    return origins


@dataclass(frozen=True)
class LLMConfig:
    """S05 provider config: which of Groq/Gemini is primary, and both providers' credentials."""

    primary: Literal["groq", "gemini"]
    groq_api_key: str
    gemini_api_key: str
    groq_model: str
    gemini_model: str
    groq_fallback_models: tuple[str, ...] = ()  # S26: extra Groq models (own quota each)
    groq_reasoning_effort: str | None = None  # S26: sent to openai/gpt-oss-* models only


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


DEFAULT_GROQ_FALLBACK_MODELS = (
    "qwen/qwen3.8-27b,openai/gpt-oss-20b"  # S26 section 2, measured order
)
REASONING_EFFORTS = ("low", "medium", "high")


def get_llm_config() -> LLMConfig:
    """GROQ_API_KEY, GEMINI_API_KEY, GROQ_MODEL, GEMINI_MODEL (required) + LLM_PROVIDER (optional,
    default "groq" per PROJECT.md section 6: "Groq (JSON mode) -> fallback Gemini Flash").
    """
    primary = os.environ.get("LLM_PROVIDER", "groq").strip().lower() or "groq"
    if primary not in ("groq", "gemini"):
        raise RuntimeError(f"LLM_PROVIDER must be 'groq' or 'gemini', got {primary!r}")
    raw_models = os.environ.get("GROQ_FALLBACK_MODELS", DEFAULT_GROQ_FALLBACK_MODELS)
    fallback_models = tuple(m.strip() for m in raw_models.split(",") if m.strip())
    effort = os.environ.get("GROQ_REASONING_EFFORT", "low").strip().lower() or None
    if effort is not None and effort not in REASONING_EFFORTS:
        raise RuntimeError(
            f"GROQ_REASONING_EFFORT must be one of {REASONING_EFFORTS}, got {effort!r}"
        )
    return LLMConfig(
        primary=primary,  # type: ignore[arg-type]
        groq_api_key=_require("GROQ_API_KEY"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        groq_model=_require("GROQ_MODEL"),
        gemini_model=_require("GEMINI_MODEL"),
        groq_fallback_models=fallback_models,
        groq_reasoning_effort=effort,
    )


@dataclass(frozen=True)
class SupabaseConfig:
    """S06 Supabase connection config. Service key only -- the core never uses the anon key."""

    url: str
    service_key: str


def get_supabase_config() -> SupabaseConfig:
    """SUPABASE_URL, SUPABASE_SERVICE_KEY (both required)."""
    return SupabaseConfig(
        url=_require("SUPABASE_URL"),
        service_key=_require("SUPABASE_SERVICE_KEY"),
    )


@dataclass(frozen=True)
class VoiceConfig:
    """S12 ASR provider config: Sarvam primary, Groq Whisper fallback."""

    sarvam_api_key: str
    sarvam_model: str
    groq_api_key: str
    groq_whisper_model: str


def get_voice_config() -> VoiceConfig:
    """SARVAM_API_KEY, SARVAM_MODEL, GROQ_WHISPER_MODEL (required). GROQ_API_KEY is reused from
    get_llm_config's env var -- same account, different model for a different task."""
    return VoiceConfig(
        sarvam_api_key=_require("SARVAM_API_KEY"),
        sarvam_model=_require("SARVAM_MODEL"),
        groq_api_key=_require("GROQ_API_KEY"),
        groq_whisper_model=_require("GROQ_WHISPER_MODEL"),
    )


@dataclass(frozen=True)
class TtsConfig:
    """S17 TTS provider config: Sarvam Bulbul, no fallback (D-S17-2)."""

    sarvam_api_key: str
    sarvam_tts_model: str
    sarvam_tts_speaker: str


def get_tts_config() -> TtsConfig:
    """SARVAM_TTS_MODEL, SARVAM_TTS_SPEAKER (required). SARVAM_API_KEY is reused from
    get_voice_config's env var -- same Sarvam account, opposite direction (speech vs. text)."""
    return TtsConfig(
        sarvam_api_key=_require("SARVAM_API_KEY"),
        sarvam_tts_model=_require("SARVAM_TTS_MODEL"),
        sarvam_tts_speaker=_require("SARVAM_TTS_SPEAKER"),
    )
