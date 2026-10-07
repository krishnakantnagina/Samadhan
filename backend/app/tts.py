"""S17 -- Text-to-speech reply (T51). Spec: docs/specs/S17-text-to-speech.md.

Default: Sarvam Bulbul only, no fallback (D-S17-2): losing a voice reply leaves the citizen with the text
reply they already have, unlike S12's ASR where a failure loses the citizen's actual input.
S32 addition: TTS_PROVIDERS=sarvam,gemini adds Gemini speech as a fallback (Sarvam ran out of credit during
testing and every spoken reply failed). With more than one provider a circuit breaker skips a dead one.

Either of us can change this file. If you do, update docs/specs/S17-text-to-speech.md and tell
the other.
"""

import base64
import io
import logging
import os
import threading
import time
import wave
from collections import OrderedDict

import httpx

from app.asr.resilience import Bulkhead, CircuitBreaker
from app.config import TtsConfig, get_tts_config

logger = logging.getLogger(__name__)

PROVIDER_TIMEOUT_SECONDS = 8.0  # same budget class as every other external call (S04 section 5)
LANGUAGE_CODE = "hi-IN"  # D-S17-1: every reply_text is backend-authored, native Hindi, always


class TtsUnavailable(RuntimeError):
    """Every TTS provider failed. S04-style mapping: 503 SERVICE_UNAVAILABLE. `status` = the provider's HTTP status, if any."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class _ProviderFailed(Exception):
    def __init__(self, message: str, *, permanent: bool = False, retry_clip: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent
        self.retry_clip = retry_clip  # a repeated or glitched clip: worth one more try


class _Busy(_ProviderFailed):
    """Too many Gemini speech calls already running: skip it for this request. Says nothing about the provider's health (no breaker failure)."""


def _sarvam_tts(text: str, config: TtsConfig) -> str:
    """Returns Sarvam's own base64 WAV string, unmodified (D-S17-4)."""
    try:
        response = httpx.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"api-subscription-key": config.sarvam_api_key},
            json={
                "text": text,
                "language_code": LANGUAGE_CODE,
                "speaker": config.sarvam_tts_speaker,
                "model": config.sarvam_tts_model,
            },
            timeout=PROVIDER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["audios"][0]
    except httpx.HTTPStatusError as exc:
        raise TtsUnavailable(f"Sarvam TTS failed: {exc}", status=exc.response.status_code) from exc
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise TtsUnavailable(f"Sarvam TTS failed: {exc}") from exc


GEMINI_TTS_TIMEOUT_SECONDS = 20.0  # a longer budget than Sarvam: the model generates the audio, it is not a lookup
GEMINI_PCM_RATE = 24000  # Gemini speech is raw 16-bit mono PCM at 24 kHz


# --- Gemini speech clean-up ------------------------------------------------------------------------------
# Measured on a real reply: a ~50 ms click before the speech, and after the sentence ended + 0.35 s of silence a
# ~150 ms burst at full volume ("crazy voice"). Both are cut here; fades remove any remaining click.

_WINDOW_MS = 20
_SILENCE_RMS = 250  # below this a 20 ms window counts as silence (speech here sits at 2000-8000)
_PAUSE_MS = 150  # silence this long separates two segments
_STRAY_MAX_MS = 600  # a segment shorter than this, next to a pause, at the very start or end is suspect
_LOUD_FACTOR = 1.8  # an end segment this much louder than the speech itself is a glitch, not a word
_FADE_MS = 15


def _rms(samples) -> float:
    return (sum(x * x for x in samples) / len(samples)) ** 0.5 if len(samples) else 0.0


def _segments(samples, win: int) -> list[tuple[int, int, float]]:
    """(start, end, rms) of each stretch of sound, split wherever there is a pause of _PAUSE_MS or more."""
    pause_windows = max(1, _PAUSE_MS // _WINDOW_MS)
    loud = [_rms(samples[i : i + win]) >= _SILENCE_RMS for i in range(0, len(samples), win)]
    out: list[tuple[int, int, float]] = []
    start = None
    quiet = 0
    for index, is_loud in enumerate(loud + [False] * pause_windows):
        if is_loud:
            if start is None:
                start = index
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet >= pause_windows:
                end = index - quiet + 1
                out.append((start * win, min(end * win, len(samples)), _rms(samples[start * win : end * win])))
                start, quiet = None, 0
    return out


def clean_pcm(pcm: bytes, rate: int = GEMINI_PCM_RATE) -> bytes:
    """Drop a stray click at the start and a loud stray burst at the end of 16-bit mono PCM; fade the edges."""
    import array

    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    win = rate * _WINDOW_MS // 1000
    segments = _segments(samples, win)
    if not segments:
        return pcm
    stray = rate * _STRAY_MAX_MS // 1000
    if len(segments) >= 2 and segments[0][1] - segments[0][0] < stray:
        segments = segments[1:]  # a short blip before the real speech
    if len(segments) >= 2:
        last = segments[-1]
        others = sorted(seg[2] for seg in segments[:-1])
        typical = others[len(others) // 2]
        if last[1] - last[0] < stray and last[2] > typical * _LOUD_FACTOR:
            segments = segments[:-1]  # a short, much louder burst after the speech has ended
    pad = rate * 120 // 1000  # keep a little natural silence around the speech
    begin = max(0, segments[0][0] - pad)
    stop = min(len(samples), segments[-1][1] + pad)
    trimmed = samples[begin:stop]
    fade = min(len(trimmed) // 2, rate * _FADE_MS // 1000)
    for i in range(fade):
        gain = i / fade
        trimmed[i] = int(trimmed[i] * gain)
        trimmed[len(trimmed) - 1 - i] = int(trimmed[len(trimmed) - 1 - i] * gain)
    return trimmed.tobytes()


def _wav_base64(pcm: bytes) -> str:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(GEMINI_PCM_RATE)
        wav.writeframes(pcm)
    return base64.b64encode(buffer.getvalue()).decode()


DEFAULT_STYLE = (
    "You are a warm, polite helpline assistant talking to a villager on the phone. "
    "Speak in natural, conversational Hindi at an unhurried pace, with a gentle, human tone. Say only this:"
)


SECONDS_PER_CHAR_LIMIT = 0.14  # normal Hindi speech measured ~0.085 s per character; above 0.14 the model repeated itself
MIN_SECONDS_LIMIT = 4.0
GEMINI_TTS_ATTEMPTS = 2  # Gemini speech is random: a repeated or glitched clip is retried once
TTS_BUDGET_SECONDS = 30.0  # whole /speak request: no new provider call or retry is started after this (a worker thread is a scarce thing)
_gemini_bulkhead = Bulkhead(int(os.environ.get("TTS_GEMINI_CONCURRENCY", "4") or 4))  # slow Gemini calls cannot eat every worker thread


def _gemini_tts(
    text: str, *, model: str | None = None, voice: str | None = None, style: str | None = None, deadline: float | None = None
) -> str:
    """Gemini speech, retried once when the clip is unusable (see _gemini_tts_once) and only while the request budget lasts."""
    if not _gemini_bulkhead.acquire():
        raise _Busy("Gemini TTS busy")
    try:
        last: _ProviderFailed | None = None
        for _ in range(GEMINI_TTS_ATTEMPTS):
            if last is not None and deadline is not None and time.monotonic() >= deadline:
                break  # out of time: give the citizen the failure now, not another 20 s wait
            try:
                return _gemini_tts_once(text, model=model, voice=voice, style=style)
            except _ProviderFailed as exc:
                if exc.permanent or not exc.retry_clip:
                    raise
                last = exc
        raise last  # type: ignore[misc]
    finally:
        _gemini_bulkhead.release()


def _gemini_tts_once(text: str, *, model: str | None, voice: str | None, style: str | None) -> str:
    """Gemini speech as a base64 WAV (same shape as Sarvam's, so the website plays it unchanged). Key in a header only."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = model or os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts").strip()
    voice = voice or os.environ.get("GEMINI_TTS_VOICE", "Kore").strip()
    style = style or os.environ.get("GEMINI_TTS_STYLE", "").strip() or DEFAULT_STYLE
    if not api_key:
        raise _ProviderFailed("Gemini TTS: GEMINI_API_KEY is not set", permanent=True)
    try:
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key},
            json={
                "contents": [{"parts": [{"text": f"{style}\n\n{text}"}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
                },
            },
            timeout=GEMINI_TTS_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise _ProviderFailed("Gemini TTS timeout") from exc
    except httpx.HTTPError as exc:  # httpx puts the URL in its message: leave it out
        raise _ProviderFailed(f"Gemini TTS network error {type(exc).__name__}") from exc
    if response.status_code >= 400:
        raise _ProviderFailed(
            f"Gemini TTS HTTP {response.status_code}", permanent=response.status_code in (401, 402, 403, 404)
        )
    try:
        part = response.json()["candidates"][0]["content"]["parts"][0]
        pcm = base64.b64decode((part.get("inlineData") or part["inline_data"])["data"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise _ProviderFailed("Gemini TTS answer malformed") from exc
    if not pcm:
        raise _ProviderFailed("Gemini TTS returned no audio")
    seconds = len(pcm) / 2 / GEMINI_PCM_RATE
    if seconds > max(MIN_SECONDS_LIMIT, len(text) * SECONDS_PER_CHAR_LIMIT):
        raise _ProviderFailed(
            f"Gemini TTS clip too long ({seconds:.0f}s for {len(text)} characters): repeated speech", retry_clip=True
        )
    return _wav_base64(clean_pcm(pcm))


_breakers: dict[str, CircuitBreaker] = {}


def _breaker(name: str) -> CircuitBreaker:
    return _breakers.setdefault(name, CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0))


def _provider_order() -> list[str]:
    raw = os.environ.get("TTS_PROVIDERS", "sarvam")
    order = [p.strip().lower() for p in raw.split(",") if p.strip()]
    unknown = [p for p in order if p not in ("sarvam", "gemini")]
    if unknown or not order:
        raise RuntimeError(f"TTS_PROVIDERS must be a list from (sarvam, gemini), got {raw!r}")
    return order


_cache: "OrderedDict[str, str]" = OrderedDict()
_cache_lock = threading.Lock()


def _cache_size() -> int:
    try:
        return max(0, int(os.environ.get("TTS_CACHE_SIZE", "0") or 0))
    except ValueError:
        return 0


def synthesize(text: str, *, config: TtsConfig | None = None) -> str:
    """Base64 WAV of `text`. Optional in-memory cache (TTS_CACHE_SIZE): bot replies repeat, so repeats cost nothing."""
    size = _cache_size()
    if size:
        with _cache_lock:
            if text in _cache:
                _cache.move_to_end(text)
                return _cache[text]
    audio = _synthesize_uncached(text, config)
    if size:
        with _cache_lock:
            _cache[text] = audio
            while len(_cache) > size:
                _cache.popitem(last=False)
    return audio


def _synthesize_uncached(text: str, config: TtsConfig | None) -> str:
    """One provider (the default) behaves exactly as before; several are tried in order."""
    order = _provider_order()
    if order == ["sarvam"]:
        return _sarvam_tts(text, config or get_tts_config())

    problems: list[str] = []
    deadline = time.monotonic() + TTS_BUDGET_SECONDS
    for name in order:
        if problems and time.monotonic() >= deadline:
            problems.append(f"{name}: skipped (request budget used up)")
            break
        breaker = _breaker(name)
        if breaker.is_open() or not breaker.allow():
            problems.append(f"{name}: skipped (breaker open)")
            continue
        try:
            audio = _sarvam_tts(text, config or get_tts_config()) if name == "sarvam" else _gemini_tts(text, deadline=deadline)
        except _Busy as exc:
            problems.append(f"{name}: {exc}")
            continue
        except (TtsUnavailable, _ProviderFailed, RuntimeError) as exc:
            permanent = (
                getattr(exc, "permanent", False)
                or getattr(exc, "status", None) in (401, 402, 403, 404)  # no credit / bad key
                or (isinstance(exc, RuntimeError) and not isinstance(exc, TtsUnavailable))  # missing config
            )
            breaker.record_failure(cooldown=300.0 if permanent else None)
            problems.append(f"{name}: {exc}")
            logger.warning("tts provider=%s failed: %s", name, exc)
            continue
        breaker.record_success()
        return audio
    raise TtsUnavailable("; ".join(problems))
