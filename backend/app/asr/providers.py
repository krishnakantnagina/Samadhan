"""S32 -- one class per speech reader. Each makes exactly ONE HTTP call and turns every failure into a ProviderError
with honest retryable/permanent flags. Retrying, pacing and fallback are the router's job, not theirs.

Secrets: keys go in headers, never in the URL, and no error message carries a key (messages are logged).
"""

import base64
import json
from typing import Protocol

import httpx

from app.asr.prompt import build_prompt
from app.asr.types import ProviderError, ReadContext, Reading

_EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/wav": "wav"}


class AudioProvider(Protocol):
    name: str

    def read(self, audio: bytes, content_type: str, context: ReadContext) -> Reading: ...


def _retry_after(response: httpx.Response) -> float | None:
    raw = getattr(response, "headers", {}).get("retry-after")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _daily_quota_spent(response: httpx.Response) -> bool:
    """Gemini says so in the body: a PerDay quota id, or a retry delay of minutes/hours. Retrying that is pointless."""
    try:
        error = response.json()["error"]
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    for detail in error.get("details", []):
        for violation in detail.get("violations", []) if isinstance(detail, dict) else []:
            if "PerDay" in str(violation.get("quotaId", "")):
                return True
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str) and delay.endswith("s") and delay[:-1].replace(".", "", 1).isdigit() and float(delay[:-1]) > 120:
            return True
    return False


def _check_status(response: httpx.Response, name: str) -> None:
    code = response.status_code
    if code < 400:
        return
    if code == 429 and _daily_quota_spent(response):
        raise ProviderError(f"{name} HTTP 429 (daily quota spent)", permanent=True, status=code)
    if code in (408, 425, 429) or code >= 500:
        raise ProviderError(f"{name} HTTP {code}", retryable=True, retry_after=_retry_after(response), status=code)
    if code in (401, 402, 403, 404):  # bad/revoked key, no credit, no access, wrong model: needs a human
        raise ProviderError(f"{name} HTTP {code}", permanent=True, status=code)
    raise ProviderError(f"{name} HTTP {code}", status=code)  # 400 etc.: this clip is the problem, not the provider


def _post(name: str, **kwargs) -> httpx.Response:
    try:
        response = httpx.post(**kwargs)
    except httpx.TimeoutException as exc:
        raise ProviderError(f"{name} timeout", retryable=True) from exc
    except httpx.HTTPError as exc:  # message deliberately omitted: httpx puts the full URL in it
        raise ProviderError(f"{name} network error {type(exc).__name__}", retryable=True) from exc
    _check_status(response, name)
    return response


def _clean_confidence(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return max(0.0, min(1.0, float(value)))


class GeminiAudioProvider:
    """Gemini hears the audio itself and uses meaning to fix dialect words (measured on 5 real clips, S32 section 1)."""

    def __init__(self, api_key: str, model: str, *, timeout: float = 15.0) -> None:
        self.name = f"gemini:{model}"  # one provider (own breaker, own rate limit) per model: each has its own quota
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def read(self, audio: bytes, content_type: str, context: ReadContext) -> Reading:
        response = _post(
            self.name,
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
            headers={"x-goog-api-key": self._api_key},
            json={
                "contents": [
                    {
                        "parts": [
                            {"text": build_prompt(context)},
                            {"inline_data": {"mime_type": content_type, "data": base64.b64encode(audio).decode()}},
                        ]
                    }
                ],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
            },
            timeout=self._timeout,
        )
        try:
            body = response.json()
            data = json.loads(body["candidates"][0]["content"]["parts"][0]["text"])
            transcript = data["transcript"]
            if not isinstance(transcript, str):
                raise TypeError("transcript is not text")
        except (KeyError, IndexError, TypeError, ValueError) as exc:  # includes JSONDecodeError
            raise ProviderError("gemini answer malformed", retryable=True) from exc
        plain = data.get("plain_hindi")
        audible = data.get("audible", True) is not False and bool(transcript.strip())
        return Reading(
            transcript=transcript.strip() if audible else "",
            plain_hindi=plain.strip() if isinstance(plain, str) and audible else None,
            confidence=_clean_confidence(data.get("confidence")),
            audible=audible,
            provider=self.name,
        )


class SarvamProvider:
    """Fast and cheap, but a plain transcriber: it does not use meaning to repair dialect words."""

    name = "sarvam"

    def __init__(self, api_key: str, model: str, *, language: str = "hi-IN", timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language
        self._timeout = timeout

    def read(self, audio: bytes, content_type: str, context: ReadContext) -> Reading:
        response = _post(
            self.name,
            url="https://api.sarvam.ai/speech-to-text",
            headers={"api-subscription-key": self._api_key},
            files={"file": (f"audio.{_EXT.get(content_type, 'webm')}", audio, content_type)},
            data={"model": self._model, "language_code": self._language, "mode": "transcribe"},
            timeout=self._timeout,
        )
        try:
            transcript = response.json()["transcript"]
            if not isinstance(transcript, str):
                raise TypeError("transcript is not text")
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("sarvam answer malformed", retryable=True) from exc
        text = transcript.strip()
        return Reading(transcript=text, plain_hindi=None, confidence=None, audible=bool(text), provider=self.name)


class GroqWhisperProvider:
    """Last resort only. Measured on dialect Hindi it returned gibberish (and Icelandic), so it is not in the default chain."""

    name = "whisper"

    def __init__(self, api_key: str, model: str, *, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def read(self, audio: bytes, content_type: str, context: ReadContext) -> Reading:
        response = _post(
            self.name,
            url="https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            files={"file": (f"audio.{_EXT.get(content_type, 'webm')}", audio, content_type)},
            data={"model": self._model, "language": "hi"},
            timeout=self._timeout,
        )
        try:
            text = str(response.json()["text"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("whisper answer malformed", retryable=True) from exc
        return Reading(transcript=text, plain_hindi=None, confidence=0.3, audible=bool(text), provider=self.name)
