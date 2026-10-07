"""S12 -- Voice (T26). Spec: docs/specs/S12-voice.md.

No FFmpeg (D-S12-1): both Sarvam and Groq Whisper accept the four ACCEPTED_AUDIO_TYPES natively, so
the browser-recorded bytes go straight through, unconverted. Storage upload happens before
transcription is attempted, unconditionally (D-S12-3, PROJECT.md section 7/13).

Either of us can change this file. If you do, update docs/specs/S12-voice.md and tell the other.
"""

import logging
import os
import uuid
from dataclasses import dataclass

import httpx
from supabase import Client

from app.asr.router import get_router
from app.asr.types import AllProvidersFailed, ReadContext
from app.config import VoiceConfig, get_voice_config
from app.db import get_client

logger = logging.getLogger(__name__)

PROVIDER_TIMEOUT_SECONDS = 8.0  # PROJECT.md section 7, S04 section 5

EXT_BY_CONTENT_TYPE = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/wav": "wav",
}


class VoiceUnavailable(RuntimeError):
    """Both ASR providers failed. S04 maps this to 503 SERVICE_UNAVAILABLE."""


@dataclass(frozen=True)
class VoiceResult:
    transcript: str  # possibly empty -- not a failure, S01 D-A6
    audio_path: str | None  # None when the recording could not be stored (the citizen is still understood)
    plain_hindi: str | None = None  # S32: standard-Hindi version for officers (router pipeline only)
    provider: str | None = None  # S32: which reader produced it (router pipeline only)


def _upload(
    audio_bytes: bytes,
    content_type: str,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    *,
    client: Client,
) -> str:
    ext = EXT_BY_CONTENT_TYPE[content_type]
    path = f"{session_id}/{message_id}.{ext}"
    client.storage.from_("audio").upload(
        path, audio_bytes, file_options={"content-type": content_type}
    )
    return path


def _filename(content_type: str) -> str:
    # Groq's API validates the filename's extension, not just the content-type header/actual
    # bytes -- a real 400 unsupported_audio_format was hit live with an extensionless filename.
    return f"audio.{EXT_BY_CONTENT_TYPE[content_type]}"


def _language() -> str:
    """Language sent to the readers. Hindi by default: with "unknown" Sarvam sometimes picks another script (a Gujarati-script transcript of a Hindi voice note
    was seen on 2026-10-07) and Whisper turns dialect into gibberish. VOICE_LANGUAGE=unknown restores auto-detect."""
    return os.environ.get("VOICE_LANGUAGE", "").strip() or "hi-IN"


def _sarvam(audio_bytes: bytes, content_type: str, config: VoiceConfig) -> str:
    response = httpx.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": config.sarvam_api_key},
        files={"file": (_filename(content_type), audio_bytes, content_type)},
        data={"model": config.sarvam_model, "language_code": _language(), "mode": "transcribe"},
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["transcript"]


def _groq_whisper(audio_bytes: bytes, content_type: str, config: VoiceConfig) -> str:
    response = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {config.groq_api_key}"},
        files={"file": (_filename(content_type), audio_bytes, content_type)},
        data={"model": config.groq_whisper_model, **({"language": _language()[:2]} if _language() != "unknown" else {})},
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["text"]


def _transcribe_with_router(
    audio_bytes: bytes, content_type: str, audio_path: str | None, context: str | None
) -> VoiceResult:
    """S32: Gemini-first reader with rate limiting, breakers, retries and fallback (app/asr)."""
    try:
        reading = get_router().read(audio_bytes, content_type, ReadContext(last_bot_question=context))
    except AllProvidersFailed as exc:
        raise VoiceUnavailable(f"audio readers failed: {exc}") from exc
    return VoiceResult(
        transcript=reading.transcript,
        audio_path=audio_path,
        plain_hindi=reading.plain_hindi,
        provider=reading.provider,
    )


def transcribe(
    audio_bytes: bytes,
    content_type: str,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    *,
    client: Client | None = None,
    context: str | None = None,
) -> VoiceResult:
    client = client or get_client()
    try:
        audio_path = _upload(audio_bytes, content_type, session_id, message_id, client=client)
    except Exception as exc:  # noqa: BLE001 -- storage down: the citizen's words matter more than the recording (audit M7)
        logger.warning("audio upload failed (%s): transcribing without storing the recording", type(exc).__name__)
        audio_path = None

    if os.environ.get("ASR_PIPELINE", "legacy").strip().lower() == "router":
        return _transcribe_with_router(audio_bytes, content_type, audio_path, context)

    config = get_voice_config()
    for attempt in (_sarvam, _groq_whisper):
        try:
            transcript = attempt(audio_bytes, content_type, config)
            return VoiceResult(transcript=transcript, audio_path=audio_path)
        except httpx.HTTPStatusError as exc:
            # Never silently swallow the reason -- a wrong model id, expired key, or oversized
            # payload all look identical (both providers "failed") to the citizen by design, but
            # that must not mean invisible to us too. Log, then fall through (one attempt each,
            # no retry -- same posture as S05 D-S05-4).
            body = getattr(exc.response, "text", "<no body>")
            logger.warning("%s failed: HTTP %s -- %s", attempt.__name__, exc.response.status_code, body[:500])
            continue
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("%s failed: %s: %s", attempt.__name__, type(exc).__name__, exc)
            continue

    raise VoiceUnavailable("both ASR providers failed")
