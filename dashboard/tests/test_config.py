"""S13 -- dashboard/config.py. Mirrors backend/tests/test_config.py's pattern."""

import pytest

from dashboard.config import get_dashboard_config

REQUIRED = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "DASHBOARD_PASSWORD"]


def _set_all(monkeypatch, **overrides):
    values = {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "key", "DASHBOARD_PASSWORD": "pw"}
    values.update(overrides)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("missing", REQUIRED)
def test_missing_var_raises(monkeypatch, missing):
    _set_all(monkeypatch)
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(RuntimeError, match=missing):
        get_dashboard_config()


def test_blank_var_raises(monkeypatch):
    _set_all(monkeypatch, DASHBOARD_PASSWORD="   ")
    with pytest.raises(RuntimeError, match="DASHBOARD_PASSWORD"):
        get_dashboard_config()


def test_parses_when_all_set(monkeypatch):
    _set_all(monkeypatch)
    config = get_dashboard_config()
    assert config.supabase_url == "https://x.supabase.co"
    assert config.supabase_service_key == "key"
    assert config.dashboard_password == "pw"
