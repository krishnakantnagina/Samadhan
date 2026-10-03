"""S32 -- audio-reader settings, all from environment variables with safe defaults.

ASR_PIPELINE=legacy (default) keeps today's behaviour exactly (app/voice.py: Sarvam, then Whisper). Nothing in
this package runs until ASR_PIPELINE=router is set.
"""

import os
from dataclasses import dataclass

KNOWN_PROVIDERS = ("gemini", "sarvam", "whisper")


def _num(name: str, default: float, *, low: float, high: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number, got {raw!r}") from exc
    if not low <= value <= high:
        raise RuntimeError(f"{name} must be between {low} and {high}, got {value}")
    return value


@dataclass(frozen=True)
class AsrConfig:
    providers: tuple[str, ...]  # order = preference: first healthy one wins, the rest are fallbacks
    gemini_models: tuple[str, ...]  # tried in this order; each Gemini model has its own quota, so a spent one is skipped
    sarvam_language: str
    rpm: dict[str, float]  # requests per minute each provider may receive from this server (0 = unlimited)
    max_concurrency: int  # simultaneous calls per provider
    min_confidence: float  # below this the app asks the citizen to repeat instead of guessing
    budget_seconds: float  # total time one citizen turn may spend reading audio, retries included
    max_attempts: int  # attempts per provider (1 = no retry)
    breaker_threshold: int  # consecutive failed requests that open a provider's breaker
    breaker_cooldown: float  # seconds an opened breaker waits before one probe call
    permanent_cooldown: float  # seconds after a permanent error (no credit, bad key)
    max_queue_wait: float  # longest a call waits for a rate-limit token before trying the next provider


def _models() -> tuple[str, ...]:
    """GEMINI_ASR_MODELS (comma list), else GEMINI_ASR_MODEL, else GEMINI_MODEL."""
    raw = (
        os.environ.get("GEMINI_ASR_MODELS", "").strip()
        or os.environ.get("GEMINI_ASR_MODEL", "").strip()
        or os.environ.get("GEMINI_MODEL", "").strip()
    )
    return tuple(m.strip() for m in raw.split(",") if m.strip())


def get_asr_config() -> AsrConfig:
    providers = tuple(p.strip().lower() for p in os.environ.get("ASR_PROVIDERS", "gemini,sarvam").split(",") if p.strip())
    unknown = [p for p in providers if p not in KNOWN_PROVIDERS]
    if unknown or not providers:
        raise RuntimeError(f"ASR_PROVIDERS must be a list from {KNOWN_PROVIDERS}, got {providers!r}")
    return AsrConfig(
        providers=providers,
        gemini_models=_models(),
        sarvam_language=os.environ.get("ASR_SARVAM_LANGUAGE", "hi-IN").strip() or "hi-IN",
        rpm={
            "gemini": _num("ASR_GEMINI_RPM", 600, low=0, high=100000),
            "sarvam": _num("ASR_SARVAM_RPM", 300, low=0, high=100000),
            "whisper": _num("ASR_WHISPER_RPM", 100, low=0, high=100000),
        },
        max_concurrency=int(_num("ASR_MAX_CONCURRENCY", 32, low=1, high=1000)),
        min_confidence=_num("ASR_MIN_CONFIDENCE", 0.5, low=0, high=1),
        budget_seconds=_num("ASR_BUDGET_SECONDS", 20, low=1, high=120),
        max_attempts=int(_num("ASR_MAX_ATTEMPTS", 2, low=1, high=5)),
        breaker_threshold=int(_num("ASR_BREAKER_THRESHOLD", 5, low=1, high=100)),
        breaker_cooldown=_num("ASR_BREAKER_COOLDOWN", 30, low=1, high=3600),
        permanent_cooldown=_num("ASR_PERMANENT_COOLDOWN", 300, low=1, high=86400),
        max_queue_wait=_num("ASR_MAX_QUEUE_WAIT", 2, low=0, high=30),
    )
