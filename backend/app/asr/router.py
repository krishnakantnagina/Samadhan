"""S32 -- ReaderRouter: reads one recording through an ordered list of providers, protecting each one and the citizen's wait.

Per request: for each provider in order -> skip if its breaker is open -> wait briefly for a rate-limit token ->
take a concurrency slot -> call (retry a transient failure with backoff + jitter, inside one time budget) -> on
success apply the quality gate. Failures fall through to the next provider; when none works AllProvidersFailed is raised.

Quality gate: not audible, or confidence under ASR_MIN_CONFIDENCE -> the reading's transcript is "" so the existing
"please repeat" reply is sent (S01 D-A6). A low-confidence answer first gets a second opinion from the next provider.
"""

import functools
import logging
import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from app.asr.config import AsrConfig, get_asr_config
from app.asr.providers import (
    AudioProvider,
    GeminiAudioProvider,
    GroqWhisperProvider,
    SarvamProvider,
)
from app.asr.resilience import Bulkhead, CircuitBreaker, Metrics, TokenBucket
from app.asr.types import AllProvidersFailed, ProviderError, ReadContext, Reading

logger = logging.getLogger(__name__)

BACKOFF_BASE_SECONDS = 0.4
BACKOFF_CAP_SECONDS = 2.0
RETRY_AFTER_CAP_SECONDS = 3.0  # a citizen is waiting: never obey a long Retry-After in the request path


@dataclass
class _Slot:
    provider: AudioProvider
    bucket: TokenBucket
    breaker: CircuitBreaker
    bulkhead: Bulkhead


class ReaderRouter:
    def __init__(
        self,
        providers: list[AudioProvider],
        config: AsrConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
        metrics: Metrics | None = None,
    ) -> None:
        self._config = config
        self._clock = clock
        self._sleep = sleep
        self._rng = rng
        self.metrics = metrics or Metrics()
        self._slots = [
            _Slot(
                provider=p,
                bucket=TokenBucket(config.rpm.get(p.name, config.rpm.get(p.name.split(":")[0])), clock=clock, sleep=sleep),
                breaker=CircuitBreaker(
                    failure_threshold=config.breaker_threshold, cooldown_seconds=config.breaker_cooldown, clock=clock
                ),
                bulkhead=Bulkhead(config.max_concurrency),
            )
            for p in providers
        ]

    def breaker_states(self) -> dict[str, str]:
        return {s.provider.name: s.breaker.state for s in self._slots}

    def read(self, audio: bytes, content_type: str, context: ReadContext | None = None) -> Reading:
        context = context or ReadContext()
        started = self._clock()
        deadline = started + self._config.budget_seconds
        low_confidence: Reading | None = None
        notes: list[str] = []

        for slot in self._slots:
            name = slot.provider.name
            if self._clock() >= deadline:
                notes.append("budget used up")
                break
            if slot.breaker.is_open():
                self.metrics.count(name, "skipped_breaker_open")
                notes.append(f"{name}: breaker open")
                continue
            reading = self._try_provider(slot, audio, content_type, context, deadline, notes)
            if reading is None:
                continue
            if not reading.audible:
                return reading  # noise or silence is a real answer, not a failure: ask the citizen to repeat
            if reading.confidence is not None and reading.confidence < self._config.min_confidence:
                self.metrics.count(name, "low_confidence")
                low_confidence = low_confidence or reading
                notes.append(f"{name}: low confidence {reading.confidence:.2f}")
                continue  # second opinion from the next provider
            return reading

        if low_confidence is not None:
            return replace(low_confidence, transcript="", plain_hindi=None)  # nobody was sure: ask to repeat
        raise AllProvidersFailed("; ".join(notes) or "no audio reader configured")

    # --- one provider -------------------------------------------------------------------------------

    def _try_provider(
        self,
        slot: _Slot,
        audio: bytes,
        content_type: str,
        context: ReadContext,
        deadline: float,
        notes: list[str],
    ) -> Reading | None:
        name = slot.provider.name
        cfg = self._config
        for attempt in range(1, cfg.max_attempts + 1):
            wait = max(0.0, min(cfg.max_queue_wait, deadline - self._clock()))
            if not slot.bucket.acquire(max_wait=wait):
                self.metrics.count(name, "rate_limited")
                notes.append(f"{name}: rate limit")
                return None
            if not slot.bulkhead.acquire(timeout=wait):
                self.metrics.count(name, "busy")
                notes.append(f"{name}: too many in flight")
                return None
            if not slot.breaker.allow():  # half-open: another request already holds the single probe
                slot.bulkhead.release()
                self.metrics.count(name, "skipped_breaker_open")
                notes.append(f"{name}: breaker open")
                return None
            began = self._clock()
            try:
                reading = slot.provider.read(audio, content_type, context)
            except ProviderError as exc:
                self._on_failure(slot, exc, attempt, notes)
                if exc.permanent or not exc.retryable or attempt == cfg.max_attempts:
                    slot.breaker.record_failure(cooldown=cfg.permanent_cooldown if exc.permanent else None)
                    return None
                delay = self._backoff(attempt, exc.retry_after)
                if self._clock() + delay >= deadline:
                    slot.breaker.record_failure()
                    return None
                slot.breaker.release_probe()
                self._sleep(delay)
                continue
            except Exception:  # a bug in a provider must not take the citizen's request down with it
                logger.exception("asr provider=%s crashed", name)
                self.metrics.count(name, "crash")
                notes.append(f"{name}: crashed")
                slot.breaker.record_failure()
                return None
            finally:
                slot.bulkhead.release()
            ms = int((self._clock() - began) * 1000)
            slot.breaker.record_success()
            self.metrics.count(name, "ok")
            self.metrics.observe_latency(name, ms)
            logger.info("asr provider=%s outcome=ok attempts=%d ms=%d conf=%s", name, attempt, ms, reading.confidence)
            return replace(reading, provider=name, latency_ms=ms, attempts=attempt)
        return None

    def _on_failure(self, slot: _Slot, exc: ProviderError, attempt: int, notes: list[str]) -> None:
        name = slot.provider.name
        kind = "permanent" if exc.permanent else "retryable" if exc.retryable else "rejected"
        self.metrics.count(name, f"fail_{kind}")
        notes.append(f"{name}: {exc}")
        logger.warning("asr provider=%s outcome=fail_%s attempt=%d status=%s reason=%s", name, kind, attempt, exc.status, exc)

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        base = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
        delay = base * (0.5 + self._rng() / 2)  # jitter, so many retries do not land at the same instant
        if retry_after is not None:
            delay = max(delay, min(retry_after, RETRY_AFTER_CAP_SECONDS))
        return delay


# --- wiring ------------------------------------------------------------------------------------------


def build_providers(config: AsrConfig) -> list[AudioProvider]:
    """The providers named in ASR_PROVIDERS, in that order. A provider whose key is missing is skipped with a warning,
    so a half-configured server still serves voice from the rest."""
    env = os.environ
    built: list[AudioProvider] = []
    for name in config.providers:
        if name == "gemini" and env.get("GEMINI_API_KEY") and config.gemini_models:
            built.extend(GeminiAudioProvider(env["GEMINI_API_KEY"], model) for model in config.gemini_models)
        elif name == "sarvam" and env.get("SARVAM_API_KEY") and env.get("SARVAM_MODEL"):
            built.append(SarvamProvider(env["SARVAM_API_KEY"], env["SARVAM_MODEL"], language=config.sarvam_language))
        elif name == "whisper" and env.get("GROQ_API_KEY") and env.get("GROQ_WHISPER_MODEL"):
            built.append(GroqWhisperProvider(env["GROQ_API_KEY"], env["GROQ_WHISPER_MODEL"]))
        else:
            logger.warning("asr provider %s is listed in ASR_PROVIDERS but not configured; skipped", name)
    return built


@functools.lru_cache(maxsize=1)
def get_router() -> ReaderRouter:
    """One router per process, so breaker and rate-limit state is shared by every request."""
    config = get_asr_config()
    return ReaderRouter(build_providers(config), config)


def reset_router() -> None:
    get_router.cache_clear()
