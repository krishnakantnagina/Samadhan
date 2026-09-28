"""S17 Text-to-speech (T51): synthesize() against mocked httpx.post calls -- no network, no real
credentials.
"""

import httpx
import pytest

import app.tts as tts_module
from app.config import TtsConfig
from app.tts import TtsUnavailable, synthesize


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.test")
            raise httpx.HTTPStatusError("error", request=request, response=self)

    def json(self):
        return self._json


CONFIG = TtsConfig(
    sarvam_api_key="sarvam-key", sarvam_tts_model="bulbul:v3", sarvam_tts_speaker="shubh"
)


def test_synthesize_returns_first_audio_and_uses_fixed_hindi(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse({"request_id": "r1", "audios": ["base64data"]})

    monkeypatch.setattr(tts_module.httpx, "post", fake_post)

    result = synthesize("नमस्ते", config=CONFIG)

    assert result == "base64data"
    assert captured["url"] == "https://api.sarvam.ai/text-to-speech"
    assert captured["headers"]["api-subscription-key"] == "sarvam-key"
    assert captured["json"]["language_code"] == "hi-IN"  # D-S17-1: always fixed
    assert captured["json"]["text"] == "नमस्ते"
    assert captured["json"]["speaker"] == "shubh"
    assert captured["json"]["model"] == "bulbul:v3"


def test_synthesize_raises_on_http_error(monkeypatch):
    def fake_post(url, **kwargs):
        return _FakeResponse(status_code=500)

    monkeypatch.setattr(tts_module.httpx, "post", fake_post)

    with pytest.raises(TtsUnavailable):
        synthesize("नमस्ते", config=CONFIG)


def test_synthesize_raises_on_empty_audios(monkeypatch):
    def fake_post(url, **kwargs):
        return _FakeResponse({"request_id": "r1", "audios": []})

    monkeypatch.setattr(tts_module.httpx, "post", fake_post)

    with pytest.raises(TtsUnavailable):
        synthesize("नमस्ते", config=CONFIG)


def test_synthesize_raises_on_malformed_response(monkeypatch):
    def fake_post(url, **kwargs):
        return _FakeResponse({"unexpected": "shape"})  # no "audios" key -> KeyError

    monkeypatch.setattr(tts_module.httpx, "post", fake_post)

    with pytest.raises(TtsUnavailable):
        synthesize("नमस्ते", config=CONFIG)
