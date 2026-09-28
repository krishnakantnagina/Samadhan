"""S12 Voice (T26): transcribe() against mocked httpx.post calls and a fake storage client -- no
network, no real credentials.
"""

import uuid

import httpx
import pytest

import app.voice as voice_module
from app.voice import VoiceUnavailable, transcribe


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


class FakeStorage:
    def __init__(self):
        self.uploads: list[tuple] = []

    def from_(self, bucket):
        assert bucket == "audio"
        return self

    def upload(self, path, data, file_options=None):
        self.uploads.append((path, data, file_options))


class FakeVoiceClient:
    def __init__(self):
        self.storage = FakeStorage()


@pytest.fixture(autouse=True)
def voice_env(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-key")
    monkeypatch.setenv("SARVAM_MODEL", "saaras:v4")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")


def make_ids():
    return uuid.uuid4(), uuid.uuid4()


def test_uploads_before_transcribing(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return _FakeResponse({"transcript": "paani nahi aa raha"})

    monkeypatch.setattr(voice_module.httpx, "post", fake_post)
    client = FakeVoiceClient()
    session_id, message_id = make_ids()

    result = transcribe(b"fake-audio", "audio/webm", session_id, message_id, client=client)

    assert client.storage.uploads  # upload happened
    assert result.audio_path == f"{session_id}/{message_id}.webm"
    assert calls == ["https://api.sarvam.ai/speech-to-text"]  # Groq never called


def test_sarvam_success_skips_groq(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return _FakeResponse({"transcript": "hello"})

    monkeypatch.setattr(voice_module.httpx, "post", fake_post)
    client = FakeVoiceClient()
    session_id, message_id = make_ids()

    result = transcribe(b"audio", "audio/wav", session_id, message_id, client=client)

    assert result.transcript == "hello"
    assert len(calls) == 1


def test_sarvam_failure_falls_back_to_groq(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if "sarvam" in url:
            return _FakeResponse(status_code=500)
        return _FakeResponse({"text": "from groq"})

    monkeypatch.setattr(voice_module.httpx, "post", fake_post)
    client = FakeVoiceClient()
    session_id, message_id = make_ids()

    result = transcribe(b"audio", "audio/ogg", session_id, message_id, client=client)

    assert result.transcript == "from groq"
    assert len(calls) == 2


def test_both_fail_raises_voice_unavailable(monkeypatch):
    def fake_post(url, **kwargs):
        return _FakeResponse(status_code=500)

    monkeypatch.setattr(voice_module.httpx, "post", fake_post)
    client = FakeVoiceClient()
    session_id, message_id = make_ids()

    with pytest.raises(VoiceUnavailable):
        transcribe(b"audio", "audio/mp4", session_id, message_id, client=client)

    assert client.storage.uploads  # original audio still kept (D-S12-3)


def test_malformed_json_response_falls_back(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if "sarvam" in url:
            return _FakeResponse({"unexpected": "shape"})  # no "transcript" key -> KeyError
        return _FakeResponse({"text": "from groq"})

    monkeypatch.setattr(voice_module.httpx, "post", fake_post)
    client = FakeVoiceClient()
    session_id, message_id = make_ids()

    result = transcribe(b"audio", "audio/webm", session_id, message_id, client=client)

    assert result.transcript == "from groq"
    assert len(calls) == 2


def test_empty_transcript_is_not_an_error(monkeypatch):
    monkeypatch.setattr(
        voice_module.httpx, "post", lambda url, **kwargs: _FakeResponse({"transcript": ""})
    )
    client = FakeVoiceClient()
    session_id, message_id = make_ids()

    result = transcribe(b"audio", "audio/webm", session_id, message_id, client=client)

    assert result.transcript == ""


@pytest.mark.parametrize(
    "content_type, ext",
    [("audio/webm", "webm"), ("audio/ogg", "ogg"), ("audio/mp4", "m4a"), ("audio/wav", "wav")],
)
def test_extension_mapping_for_each_accepted_content_type(monkeypatch, content_type, ext):
    monkeypatch.setattr(
        voice_module.httpx, "post", lambda url, **kwargs: _FakeResponse({"transcript": "x"})
    )
    client = FakeVoiceClient()
    session_id, message_id = make_ids()

    result = transcribe(b"audio", content_type, session_id, message_id, client=client)

    assert result.audio_path == f"{session_id}/{message_id}.{ext}"
