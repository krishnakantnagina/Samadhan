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


# --- S32: router pipeline (ASR_PIPELINE=router) --------------------------------------------------------


class _FakeRouter:
    def __init__(self, reading=None, error=None):
        self.reading, self.error, self.seen = reading, error, []

    def read(self, audio, content_type, context):
        self.seen.append((audio, content_type, context))
        if self.error:
            raise self.error
        return self.reading


def _router_mode(monkeypatch, router):
    monkeypatch.setenv("ASR_PIPELINE", "router")
    monkeypatch.setattr(voice_module, "get_router", lambda: router)


def test_router_pipeline_uploads_first_and_returns_the_reading(monkeypatch):
    from app.asr.types import Reading

    router = _FakeRouter(Reading(transcript="स्कूल में मास्टर नहीं आए", plain_hindi="शिक्षक नहीं आए", confidence=0.95, audible=True, provider="gemini"))
    _router_mode(monkeypatch, router)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("legacy providers must not be called"))
    client = FakeVoiceClient()
    session_id, message_id = make_ids()

    result = transcribe(b"audio", "audio/webm", session_id, message_id, client=client, context="कितने दिन से?")

    assert client.storage.uploads and client.storage.uploads[0][1] == b"audio"
    assert (result.transcript, result.plain_hindi, result.provider) == ("स्कूल में मास्टर नहीं आए", "शिक्षक नहीं आए", "gemini")
    assert result.audio_path == f"{session_id}/{message_id}.webm"
    assert router.seen[0][2].last_bot_question == "कितने दिन से?"


def test_router_pipeline_empty_transcript_is_not_a_failure(monkeypatch):
    from app.asr.types import Reading

    _router_mode(monkeypatch, _FakeRouter(Reading(transcript="", plain_hindi=None, confidence=0.1, audible=False, provider="gemini")))
    result = transcribe(b"x", "audio/webm", *make_ids(), client=FakeVoiceClient())
    assert result.transcript == ""


def test_router_pipeline_failure_becomes_voice_unavailable_after_upload(monkeypatch):
    from app.asr.types import AllProvidersFailed

    _router_mode(monkeypatch, _FakeRouter(error=AllProvidersFailed("gemini: HTTP 503; sarvam: breaker open")))
    client = FakeVoiceClient()
    with pytest.raises(VoiceUnavailable, match="audio readers failed"):
        transcribe(b"x", "audio/webm", *make_ids(), client=client)
    assert client.storage.uploads  # the recording is still kept (D-S12-3)


def test_default_pipeline_is_still_the_legacy_one(monkeypatch):
    monkeypatch.delenv("ASR_PIPELINE", raising=False)
    monkeypatch.setattr(voice_module, "get_router", lambda: pytest.fail("router must not run by default"))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse({"transcript": "नमस्ते"}))
    assert transcribe(b"x", "audio/webm", *make_ids(), client=FakeVoiceClient()).transcript == "नमस्ते"
