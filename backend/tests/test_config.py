"""T07 config: ALLOWED_ORIGINS parsing (backend/app/config.py)."""

import pytest

from app.config import get_allowed_origins


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
