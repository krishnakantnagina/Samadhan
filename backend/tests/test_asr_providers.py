"""S32 -- the three speech readers against a mocked httpx.post: parsing, status mapping, and that no secret leaks."""

import json

import httpx
import pytest

from app.asr.config import get_asr_config
from app.asr.prompt import GLOSSARY, build_prompt
from app.asr.providers import GeminiAudioProvider, GroqWhisperProvider, SarvamProvider
from app.asr.types import ProviderError, ReadContext

SECRET = "SECRET-KEY-123"


class FakeResponse:
    def __init__(self, json_data=None, status_code=200, headers=None):
        self._json = json_data
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def gemini_body(payload):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}


@pytest.fixture
def captured(monkeypatch):
    calls = []
    state = {"response": FakeResponse(gemini_body({"transcript": "ठीक", "plain_hindi": "ठीक", "audible": True, "confidence": 0.9}))}

    def fake_post(**kwargs):
        calls.append(kwargs)
        item = state["response"]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls, state


# --- Gemini ---------------------------------------------------------------------------------------


def test_gemini_reads_a_good_answer_and_keeps_the_key_out_of_the_url(captured):
    calls, _ = captured
    reading = GeminiAudioProvider(SECRET, "gemini-x").read(b"abc", "audio/webm", ReadContext())
    assert (reading.transcript, reading.plain_hindi, reading.confidence, reading.audible) == ("ठीक", "ठीक", 0.9, True)
    call = calls[0]
    assert SECRET not in call["url"] and call["headers"] == {"x-goog-api-key": SECRET}
    assert call["json"]["generationConfig"]["temperature"] == 0
    part = call["json"]["contents"][0]["parts"][1]["inline_data"]
    assert part["mime_type"] == "audio/webm" and part["data"] == "YWJj"


def test_gemini_not_audible_gives_an_empty_transcript(captured):
    _, state = captured
    state["response"] = FakeResponse(gemini_body({"transcript": "कुछ", "plain_hindi": "कुछ", "audible": False, "confidence": 0.1}))
    reading = GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext())
    assert reading.audible is False and reading.transcript == "" and reading.plain_hindi is None


def test_gemini_empty_transcript_counts_as_not_audible(captured):
    _, state = captured
    state["response"] = FakeResponse(gemini_body({"transcript": "  ", "audible": True, "confidence": 0.9}))
    assert GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext()).audible is False


@pytest.mark.parametrize("value,expected", [(1.7, 1.0), (-2, 0.0), ("high", None), (True, None), (None, None)])
def test_gemini_confidence_is_clamped_or_dropped(captured, value, expected):
    _, state = captured
    state["response"] = FakeResponse(gemini_body({"transcript": "ठीक", "audible": True, "confidence": value}))
    assert GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext()).confidence == expected


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse({"candidates": []}),
        FakeResponse({"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}),
        FakeResponse(gemini_body({"no_transcript": 1})),
        FakeResponse(gemini_body({"transcript": 5})),
        FakeResponse({}),
    ],
)
def test_gemini_malformed_answers_are_retryable_errors(captured, response):
    _, state = captured
    state["response"] = response
    with pytest.raises(ProviderError) as info:
        GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext())
    assert info.value.retryable and not info.value.permanent


@pytest.mark.parametrize(
    "status,retryable,permanent",
    [(429, True, False), (503, True, False), (500, True, False), (408, True, False),
     (401, False, True), (402, False, True), (403, False, True), (404, False, True),
     (400, False, False)],
)
def test_status_codes_map_to_honest_flags(captured, status, retryable, permanent):
    _, state = captured
    state["response"] = FakeResponse({}, status_code=status)
    with pytest.raises(ProviderError) as info:
        GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext())
    assert (info.value.retryable, info.value.permanent, info.value.status) == (retryable, permanent, status)


def test_retry_after_header_is_passed_on(captured):
    _, state = captured
    state["response"] = FakeResponse({}, status_code=429, headers={"retry-after": "7"})
    with pytest.raises(ProviderError) as info:
        GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext())
    assert info.value.retry_after == 7.0


def test_network_errors_are_retryable_and_never_leak_the_url_or_key(captured):
    _, state = captured
    for exc in (httpx.ReadTimeout("slow"), httpx.ConnectError(f"https://x/?key={SECRET}")):
        state["response"] = exc
        with pytest.raises(ProviderError) as info:
            GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext())
        assert info.value.retryable and SECRET not in str(info.value)


# --- Sarvam and Whisper ---------------------------------------------------------------------------


def test_sarvam_forces_hindi_by_default_and_sends_the_key_as_a_header(captured):
    calls, state = captured
    state["response"] = FakeResponse({"transcript": " नल खराब "})
    reading = SarvamProvider(SECRET, "saaras:v4").read(b"x", "audio/webm", ReadContext())
    assert reading.transcript == "नल खराब" and reading.confidence is None and reading.audible
    assert calls[0]["data"]["language_code"] == "hi-IN" and calls[0]["headers"] == {"api-subscription-key": SECRET}


def test_sarvam_empty_transcript_is_not_audible(captured):
    _, state = captured
    state["response"] = FakeResponse({"transcript": ""})
    assert SarvamProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext()).audible is False


def test_sarvam_402_is_permanent(captured):
    _, state = captured
    state["response"] = FakeResponse({}, status_code=402)
    with pytest.raises(ProviderError) as info:
        SarvamProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext())
    assert info.value.permanent


def test_whisper_forces_hindi_and_has_low_confidence(captured):
    calls, state = captured
    state["response"] = FakeResponse({"text": "चाहर दोंसे"})
    reading = GroqWhisperProvider(SECRET, "whisper-x").read(b"x", "audio/webm", ReadContext())
    assert calls[0]["data"]["language"] == "hi" and reading.confidence == 0.3


# --- prompt and config ----------------------------------------------------------------------------


def test_prompt_has_glossary_context_and_the_injection_guard():
    prompt = build_prompt(ReadContext(last_bot_question="यह समस्या कितने दिनों से है?"))
    assert all(line in prompt for line in GLOSSARY)
    assert "कितने दिनों से" in prompt and "never as instructions" in prompt
    assert "last question" not in build_prompt(ReadContext()) and "last question" not in build_prompt(None)


def test_prompt_context_is_truncated():
    assert len(build_prompt(ReadContext(last_bot_question="क" * 5000))) < len(build_prompt(None)) + 700


def test_config_defaults(monkeypatch):
    for name in ("ASR_PROVIDERS", "GEMINI_ASR_MODEL", "ASR_GEMINI_RPM", "ASR_MIN_CONFIDENCE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    cfg = get_asr_config()
    assert cfg.providers == ("gemini", "sarvam") and cfg.gemini_models == ("gemini-test",)
    assert cfg.min_confidence == 0.5 and cfg.rpm["gemini"] == 600


@pytest.mark.parametrize(
    "name,value", [("ASR_PROVIDERS", "gemini,openai"), ("ASR_PROVIDERS", " , "), ("ASR_MIN_CONFIDENCE", "2"),
                   ("ASR_MAX_ATTEMPTS", "zero"), ("ASR_BUDGET_SECONDS", "0")],
)
def test_config_rejects_bad_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError):
        get_asr_config()


def test_a_list_of_gemini_models_becomes_one_provider_each_in_order(monkeypatch):
    from app.asr.router import build_providers

    monkeypatch.setenv("GEMINI_ASR_MODELS", "gemini-a, gemini-b ,gemini-c")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("SARVAM_API_KEY", "s")
    monkeypatch.setenv("SARVAM_MODEL", "m")
    monkeypatch.setenv("ASR_PROVIDERS", "gemini,sarvam")
    names = [p.name for p in build_providers(get_asr_config())]
    assert names == ["gemini:gemini-a", "gemini:gemini-b", "gemini:gemini-c", "sarvam"]


def test_models_list_beats_single_model_beats_default(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "main")
    monkeypatch.delenv("GEMINI_ASR_MODELS", raising=False)
    monkeypatch.delenv("GEMINI_ASR_MODEL", raising=False)
    assert get_asr_config().gemini_models == ("main",)
    monkeypatch.setenv("GEMINI_ASR_MODEL", "single")
    assert get_asr_config().gemini_models == ("single",)
    monkeypatch.setenv("GEMINI_ASR_MODELS", "x,y")
    assert get_asr_config().gemini_models == ("x", "y")


def test_each_gemini_model_uses_the_gemini_rate_limit(monkeypatch):
    from app.asr.router import ReaderRouter

    monkeypatch.setenv("GEMINI_MODEL", "m")
    cfg = get_asr_config()
    router = ReaderRouter([GeminiAudioProvider("k", "gemini-a")], cfg)
    assert router._slots[0].bucket._rate == cfg.rpm["gemini"] / 60


def test_a_spent_daily_quota_is_permanent_so_it_is_not_retried(captured):
    _, state = captured
    body = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}, {"retryDelay": "35996s"}]}}
    state["response"] = FakeResponse(body, status_code=429)
    with pytest.raises(ProviderError) as info:
        GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext())
    assert info.value.permanent and not info.value.retryable


def test_a_long_retry_delay_alone_also_counts_as_spent(captured):
    _, state = captured
    state["response"] = FakeResponse({"error": {"details": [{"retryDelay": "600s"}]}}, status_code=429)
    with pytest.raises(ProviderError) as info:
        GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext())
    assert info.value.permanent


def test_a_per_minute_429_stays_retryable(captured):
    _, state = captured
    state["response"] = FakeResponse({"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel"}]}, {"retryDelay": "12s"}]}}, status_code=429)
    with pytest.raises(ProviderError) as info:
        GeminiAudioProvider(SECRET, "m").read(b"x", "audio/webm", ReadContext())
    assert info.value.retryable and not info.value.permanent
