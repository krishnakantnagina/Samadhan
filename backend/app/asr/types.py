"""S32 -- shared types for the audio reader (app/asr). Spec: docs/specs/S32-asr-router.md."""

from dataclasses import dataclass


class ProviderError(Exception):
    """One provider call failed. The router decides what to do from these flags, never from the message.

    retryable: worth another attempt now (429, 5xx, timeout, malformed answer).
    permanent: the provider cannot work until a human fixes something (bad key, no credit, bad request);
               the router opens its circuit breaker for a long time at once.
    The message must never contain a key or a URL with a key in it (it is logged).
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        permanent: bool = False,
        retry_after: float | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.permanent = permanent
        self.retry_after = retry_after
        self.status = status


class AllProvidersFailed(RuntimeError):
    """No provider produced a reading inside the time budget. voice.py maps this to VoiceUnavailable (503)."""


@dataclass(frozen=True)
class ReadContext:
    """What the reader may know besides the audio. All optional."""

    last_bot_question: str | None = None  # lets a one-word answer ("हाँ", "चार दिन") be read in context


@dataclass(frozen=True)
class Reading:
    transcript: str  # what was said, in Devanagari; "" when nothing usable (the app then asks to repeat)
    plain_hindi: str | None  # the same meaning in standard Hindi (for officers); None if the provider cannot
    confidence: float | None  # 0..1, None when the provider gives none
    audible: bool  # False = noise/silence, no clear speech
    provider: str = ""
    latency_ms: int = 0
    attempts: int = 1
