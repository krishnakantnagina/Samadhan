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


# --- S32: Gemini speech as a fallback (TTS_PROVIDERS=sarvam,gemini) ------------------------------------------

import base64
import io
import wave


@pytest.fixture(autouse=True)
def _fresh_breakers():
    tts_module._breakers.clear()
    yield
    tts_module._breakers.clear()


class _Resp:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data if json_data is not None else {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("e", request=httpx.Request("POST", "https://x.test"), response=self)

    def json(self):
        return self._json


def _gemini_ok(pcm=b"\x01\x00" * 2400):
    return _Resp({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]})


def _both(monkeypatch, sarvam, gemini, calls):
    monkeypatch.setenv("TTS_PROVIDERS", "sarvam,gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-SECRET")

    def fake_post(url=None, **kwargs):
        calls.append((url, kwargs))
        item = sarvam if "sarvam" in url else gemini
        return item() if callable(item) else item

    monkeypatch.setattr(tts_module.httpx, "post", fake_post)


def test_fallback_to_gemini_when_sarvam_has_no_credit_returns_a_playable_wav(monkeypatch):
    calls = []
    _both(monkeypatch, _Resp(status_code=402), _gemini_ok(), calls)

    audio = synthesize("नमस्ते", config=CONFIG)

    with wave.open(io.BytesIO(base64.b64decode(audio))) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (1, 2, 24000, 2400)
    gemini_call = next(c for c in calls if "generativelanguage" in c[0])[1]
    assert "gem-SECRET" not in str(calls[1][0]) and gemini_call["headers"] == {"x-goog-api-key": "gem-SECRET"}
    assert gemini_call["json"]["generationConfig"]["responseModalities"] == ["AUDIO"]


def test_a_dead_sarvam_is_skipped_on_later_replies(monkeypatch):
    calls = []
    _both(monkeypatch, _Resp(status_code=402), _gemini_ok(), calls)
    synthesize("एक", config=CONFIG)
    synthesize("दो", config=CONFIG)
    synthesize("तीन", config=CONFIG)
    assert sum("sarvam" in c[0] for c in calls) == 1  # one 402, then the breaker keeps it out of the way
    assert sum("generativelanguage" in c[0] for c in calls) == 3


def test_sarvam_wins_when_it_works(monkeypatch):
    calls = []
    _both(monkeypatch, _Resp({"audios": ["sarvam-audio"]}), _gemini_ok(), calls)
    assert synthesize("नमस्ते", config=CONFIG) == "sarvam-audio"
    assert not any("generativelanguage" in c[0] for c in calls)


def test_a_temporary_sarvam_error_does_not_lock_it_out_for_minutes(monkeypatch):
    calls = []
    _both(monkeypatch, _Resp(status_code=500), _gemini_ok(), calls)
    synthesize("एक", config=CONFIG)
    assert tts_module._breaker("sarvam").state == "closed"  # one 500 is not "no credit"


def test_every_provider_failing_raises_without_leaking_the_key(monkeypatch):
    calls = []
    _both(monkeypatch, _Resp(status_code=402), _Resp(status_code=503), calls)
    with pytest.raises(TtsUnavailable) as info:
        synthesize("नमस्ते", config=CONFIG)
    assert "gem-SECRET" not in str(info.value) and "gemini" in str(info.value)


@pytest.mark.parametrize("bad", [_Resp({}), _Resp({"candidates": []}), _Resp({"candidates": [{"content": {"parts": [{"inlineData": {"data": ""}}]}}]})])
def test_malformed_gemini_audio_is_a_failure_not_a_crash(monkeypatch, bad):
    _both(monkeypatch, _Resp(status_code=402), bad, [])
    with pytest.raises(TtsUnavailable):
        synthesize("नमस्ते", config=CONFIG)


def test_missing_gemini_key_is_reported_and_unknown_providers_rejected(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDERS", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(TtsUnavailable, match="GEMINI_API_KEY"):
        synthesize("नमस्ते", config=CONFIG)
    monkeypatch.setenv("TTS_PROVIDERS", "sarvam,openai")
    with pytest.raises(RuntimeError, match="TTS_PROVIDERS"):
        synthesize("नमस्ते", config=CONFIG)


# --- S32: Gemini speech is random: guards for repeated speech, plus the optional cache ----------------------------


def test_clean_pcm_removes_a_start_click_and_a_loud_end_burst():
    import array

    from app.tts import clean_pcm

    rate = 24000

    def tone(ms, amp):
        return [amp if (i // 20) % 2 else -amp for i in range(rate * ms // 1000)]

    quiet = lambda ms: [0] * (rate * ms // 1000)
    samples = quiet(50) + tone(40, 3000) + quiet(250) + tone(3000, 4000) + quiet(350) + tone(150, 20000)
    out = array.array("h")
    out.frombytes(clean_pcm(array.array("h", samples).tobytes()))
    assert max(abs(x) for x in out) <= 4000  # the 20000-high end burst is gone
    assert len(out) < len(samples) - rate * 150 // 1000  # click and burst removed
    assert abs(out[0]) < 50 and abs(out[-1]) < 50  # faded edges


def test_clean_pcm_keeps_real_speech_and_a_short_quiet_last_word():
    import array

    from app.tts import clean_pcm

    rate = 24000
    tone = lambda ms, amp: [amp if (i // 20) % 2 else -amp for i in range(rate * ms // 1000)]
    samples = tone(2000, 4000) + [0] * (rate * 300 // 1000) + tone(300, 4000)  # a short final word, same loudness
    out = clean_pcm(array.array("h", samples).tobytes())
    assert len(out) >= len(samples) * 2 * 0.95  # nothing real was cut


def _long_gemini(seconds):
    return _gemini_ok(bytes([1, 0]) * (24000 * seconds))


def test_a_repeated_clip_is_retried_once_and_the_good_retry_is_used(monkeypatch):
    calls = []
    answers = [_long_gemini(30), _gemini_ok()]
    monkeypatch.setenv("TTS_PROVIDERS", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(tts_module.httpx, "post", lambda url=None, **kw: (calls.append(url), answers.pop(0))[1])
    audio = synthesize("नमस्ते, यह एक छोटा वाक्य है।", config=CONFIG)
    assert len(calls) == 2 and audio


def test_two_repeated_clips_in_a_row_fail_instead_of_playing_garbage(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDERS", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(tts_module.httpx, "post", lambda url=None, **kw: _long_gemini(30))
    with pytest.raises(TtsUnavailable, match="too long"):
        synthesize("नमस्ते, यह एक छोटा वाक्य है।", config=CONFIG)


def test_cache_is_off_by_default_and_when_on_repeats_do_not_call_the_provider(monkeypatch):
    tts_module._cache.clear()
    calls = []
    monkeypatch.setattr(tts_module.httpx, "post", lambda *a, **k: (calls.append(1), _FakeResponse({"audios": ["A"]}))[1])
    monkeypatch.delenv("TTS_CACHE_SIZE", raising=False)
    synthesize("नमस्ते", config=CONFIG)
    synthesize("नमस्ते", config=CONFIG)
    assert len(calls) == 2
    monkeypatch.setenv("TTS_CACHE_SIZE", "2")
    synthesize("एक", config=CONFIG)
    synthesize("एक", config=CONFIG)
    assert len(calls) == 3
    synthesize("दो", config=CONFIG)
    synthesize("तीन", config=CONFIG)  # evicts "एक" (size 2)
    synthesize("एक", config=CONFIG)
    assert len(calls) == 6
    tts_module._cache.clear()
