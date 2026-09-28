"""S12 -- Voice (T26). Spec: docs/specs/S12-voice.md.

No FFmpeg (D-S12-1): both Sarvam and Groq Whisper accept the four ACCEPTED_AUDIO_TYPES natively, so
the browser-recorded bytes go straight through, unconverted. Storage upload happens before
transcription is attempted, unconditionally (D-S12-3, PROJECT.md section 7/13).

Either of us can change this file. If you do, update docs/specs/S12-voice.md and tell the other.
"""

import logging
import uuid
from dataclasses import dataclass

import httpx
from supabase import Client

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
    audio_path: str


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


def _sarvam(audio_bytes: bytes, content_type: str, config: VoiceConfig) -> str:
    response = httpx.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": config.sarvam_api_key},
        files={"file": (_filename(content_type), audio_bytes, content_type)},
        data={"model": config.sarvam_model, "language_code": "unknown", "mode": "transcribe"},
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["transcript"]


def _groq_whisper(audio_bytes: bytes, content_type: str, config: VoiceConfig) -> str:
    response = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {config.groq_api_key}"},
        files={"file": (_filename(content_type), audio_bytes, content_type)},
        data={"model": config.groq_whisper_model},
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["text"]


def transcribe(
    audio_bytes: bytes,
    content_type: str,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    *,
    client: Client | None = None,
) -> VoiceResult:
    client = client or get_client()
    audio_path = _upload(audio_bytes, content_type, session_id, message_id, client=client)

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
