"""S26 LLM fallback chain: config, provider order, request body, 429 fall-through, deadline. No network."""

import httpx
import pytest

from app import turn_engine
from app.config import LLMConfig, get_llm_config
from app.turn_engine import (
    GeminiProvider,
    GroqProvider,
    SessionState,
    TurnEngineUnavailable,
    _ProviderError,
    default_providers,
    run_turn,
)
from tests.test_turn_engine import SPECS, FakeProvider, valid_json

ENV = {
    "GROQ_API_KEY": "k",
    "GEMINI_API_KEY": "g",
    "GROQ_MODEL": "openai/gpt-oss-120b",
    "GEMINI_MODEL": "gem",
}


def set_env(monkeypatch, **extra):
    for name in ("GROQ_FALLBACK_MODELS", "GROQ_REASONING_EFFORT", "LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {**ENV, **extra}.items():
        monkeypatch.setenv(name, value)


# --- config -----------------------------------------------------------------------------------


def test_config_defaults(monkeypatch):
    set_env(monkeypatch)
    config = get_llm_config()
    assert config.groq_fallback_models == ("qwen/qwen3.8-27b", "openai/gpt-oss-20b")
    assert config.groq_reasoning_effort == "low"


def test_config_custom_and_empty_fallbacks(monkeypatch):
    set_env(monkeypatch, GROQ_FALLBACK_MODELS=" a/b , c/d ,, ", GROQ_REASONING_EFFORT="HIGH")
    config = get_llm_config()
    assert config.groq_fallback_models == ("a/b", "c/d")
    assert config.groq_reasoning_effort == "high"

    set_env(monkeypatch, GROQ_FALLBACK_MODELS="", GROQ_REASONING_EFFORT="")
    config = get_llm_config()
    assert config.groq_fallback_models == ()
    assert config.groq_reasoning_effort is None


def test_config_rejects_bad_effort(monkeypatch):
    set_env(monkeypatch, GROQ_REASONING_EFFORT="extreme")
    with pytest.raises(RuntimeError, match="GROQ_REASONING_EFFORT"):
        get_llm_config()


# --- provider order ---------------------------------------------------------------------------


def config(**overrides):
    base = {
        "primary": "groq",
        "groq_api_key": "k",
        "gemini_api_key": "g",
        "groq_model": "m1",
        "gemini_model": "gem",
        "groq_fallback_models": ("m2", "m3"),
        "groq_reasoning_effort": "low",
    }
    base.update(overrides)
    return LLMConfig(**base)


def test_groq_primary_order():
    names = [p.name for p in default_providers(config())]
    assert names == ["groq:m1", "groq:m2", "groq:m3", "gemini"]


def test_gemini_primary_order():
    providers = default_providers(config(primary="gemini"))
    assert [p.name for p in providers] == ["gemini", "groq:m1", "groq:m2", "groq:m3"]
    assert isinstance(providers[0], GeminiProvider)


def test_no_extra_models_is_todays_two_provider_chain():
    names = [p.name for p in default_providers(config(groq_fallback_models=()))]
    assert names == ["groq:m1", "gemini"]


# --- request body -----------------------------------------------------------------------------


class _Resp:
    def __init__(self, status=200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.groq.com/x")
            raise httpx.HTTPStatusError(
                "err", request=request, response=httpx.Response(self.status_code, request=request)
            )

    def json(self):
        return {"choices": [{"message": {"content": "{}"}}]}


def capture_body(monkeypatch, provider):
    seen = {}

    def fake_post(url, **kwargs):
        seen.update(kwargs["json"])
        return _Resp()

    monkeypatch.setattr(turn_engine.httpx, "post", fake_post)
    provider.complete("prompt")
    return seen


def test_reasoning_effort_sent_to_gpt_oss_only(monkeypatch):
    assert (
        capture_body(monkeypatch, GroqProvider("k", "openai/gpt-oss-120b", "low"))[
            "reasoning_effort"
        ]
        == "low"
    )
    assert "reasoning_effort" not in capture_body(
        monkeypatch, GroqProvider("k", "qwen/qwen3.8-27b", "low")
    )


def test_no_effort_configured_means_none_sent(monkeypatch):
    assert "reasoning_effort" not in capture_body(
        monkeypatch, GroqProvider("k", "openai/gpt-oss-120b", None)
    )


def test_429_raises_a_provider_error_immediately(monkeypatch):
    monkeypatch.setattr(turn_engine.httpx, "post", lambda *a, **k: _Resp(429))
    monkeypatch.setattr(
        turn_engine.time,
        "sleep",
        lambda *_: pytest.fail("must not sleep on 429 (D-S26-3)"),
        raising=False,
    )
    with pytest.raises(_ProviderError, match="groq:m1"):
        GroqProvider("k", "m1").complete("prompt")


# --- run_turn over the chain ------------------------------------------------------------------


def turn(providers):
    return run_turn(
        session=SessionState(None, {}, False),
        specs=SPECS,
        text="paani nahi aa raha",
        lat=None,
        lng=None,
        providers=providers,
    )


def test_rate_limited_primary_falls_through_to_the_next_groq_model(caplog):
    limited = FakeProvider("groq:m1", error=_ProviderError("groq:m1: 429 Too Many Requests"))
    backup = FakeProvider("groq:m2", response=valid_json(fields={"issue_type": "no_supply"}))
    never = FakeProvider("gemini", error=_ProviderError("must not be reached"))

    with caplog.at_level("WARNING"):
        result = turn([limited, backup, never])

    assert result.fields == {"issue_type": "no_supply"}
    assert (limited.calls, backup.calls, never.calls) == (1, 1, 0)
    assert "groq:m1" in caplog.text and "429" in caplog.text  # the reason is now visible


def test_whole_chain_failing_is_the_existing_503():
    chain = [FakeProvider(f"p{i}", error=_ProviderError("down")) for i in range(4)]
    with pytest.raises(TurnEngineUnavailable):
        turn(chain)
    assert [p.calls for p in chain] == [1, 1, 1, 1]


def test_deadline_stops_starting_new_providers(monkeypatch):
    clock = iter([0.0, 0.0, 15.0, 15.0, 15.0])  # started, first check, then past the 14 s deadline
    monkeypatch.setattr(turn_engine.time, "monotonic", lambda: next(clock))
    slow = FakeProvider("p1", error=_ProviderError("timeout"))
    never = FakeProvider("p2", response=valid_json(fields={}))

    with pytest.raises(TurnEngineUnavailable):
        turn([slow, never])

    assert (slow.calls, never.calls) == (1, 0)
