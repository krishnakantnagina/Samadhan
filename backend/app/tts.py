"""S17 -- Text-to-speech reply (T51). Spec: docs/specs/S17-text-to-speech.md.

Sarvam Bulbul only, no fallback (D-S17-2): losing a voice reply leaves the citizen with the text
reply they already have, unlike S12's ASR where a failure loses the citizen's actual input.

Either of us can change this file. If you do, update docs/specs/S17-text-to-speech.md and tell
the other.
"""

import httpx

from app.config import TtsConfig, get_tts_config

PROVIDER_TIMEOUT_SECONDS = 8.0  # same budget class as every other external call (S04 section 5)
LANGUAGE_CODES = {
    "hi": "hi-IN",
    "en": "en-IN",
}  # D-S17-1: replies are Hindi; S30: the English greeting is spoken in en-IN


class TtsUnavailable(RuntimeError):
    """Sarvam TTS failed. S04-style mapping: 503 SERVICE_UNAVAILABLE."""


def synthesize(text: str, *, language: str = "hi", config: TtsConfig | None = None) -> str:
    """Returns Sarvam's own base64 WAV string, unmodified (D-S17-4). `language` is "hi" (default) or "en" (S30)."""
    config = config or get_tts_config()
    try:
        response = httpx.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"api-subscription-key": config.sarvam_api_key},
            json={
                "text": text,
                "language_code": LANGUAGE_CODES[language],
                "speaker": config.sarvam_tts_speaker,
                "model": config.sarvam_tts_model,
            },
            timeout=PROVIDER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["audios"][0]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise TtsUnavailable(f"Sarvam TTS failed: {exc}") from exc
