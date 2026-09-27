"""T07/T12/T14 config: ALLOWED_ORIGINS, LLM provider, and Supabase parsing (backend/app/config.py)."""

import pytest

from app.config import get_allowed_origins, get_llm_config, get_supabase_config


def test_missing_raises(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        get_allowed_origins()


def test_blank_raises(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", " , ")
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        get_allowed_origins()


def test_parses_and_trims(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://a.test, http://b.test ,,")
    assert get_allowed_origins() == ["http://a.test", "http://b.test"]


# --- get_llm_config (T12, S05-turn-engine.md) -----------------------------------------------

LLM_ENV = {
    "GROQ_API_KEY": "groq-key",
    "GEMINI_API_KEY": "gemini-key",
    "GROQ_MODEL": "groq-model",
    "GEMINI_MODEL": "gemini-model",
}


def set_llm_env(monkeypatch, **overrides):
    for name, value in {**LLM_ENV, **overrides}.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


@pytest.mark.parametrize(
    "missing", ["GROQ_API_KEY", "GEMINI_API_KEY", "GROQ_MODEL", "GEMINI_MODEL"]
)
def test_llm_config_missing_var_raises(monkeypatch, missing):
    set_llm_env(monkeypatch, **{missing: None})
    with pytest.raises(RuntimeError, match=missing):
        get_llm_config()


def test_llm_config_defaults_primary_to_groq(monkeypatch):
    set_llm_env(monkeypatch)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert get_llm_config().primary == "groq"


def test_llm_config_invalid_provider_raises(monkeypatch):
    set_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "notaprovider")
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        get_llm_config()


def test_llm_config_parses_valid_env(monkeypatch):
    set_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    config = get_llm_config()
    assert config.primary == "gemini"
    assert config.groq_api_key == "groq-key"
    assert config.gemini_api_key == "gemini-key"
    assert config.groq_model == "groq-model"
    assert config.gemini_model == "gemini-model"


# --- get_supabase_config (T14, S06-session-manager.md) --------------------------------------

SUPABASE_ENV = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_KEY": "service-key",
}


def set_supabase_env(monkeypatch, **overrides):
    for name, value in {**SUPABASE_ENV, **overrides}.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


@pytest.mark.parametrize("missing", ["SUPABASE_URL", "SUPABASE_SERVICE_KEY"])
def test_supabase_config_missing_var_raises(monkeypatch, missing):
    set_supabase_env(monkeypatch, **{missing: None})
    with pytest.raises(RuntimeError, match=missing):
        get_supabase_config()


def test_supabase_config_parses_valid_env(monkeypatch):
    set_supabase_env(monkeypatch)
    config = get_supabase_config()
    assert config.url == "https://example.supabase.co"
    assert config.service_key == "service-key"
