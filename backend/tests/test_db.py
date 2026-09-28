"""T14/T27: app/db.py's cached Supabase client factory and its explicit timeouts."""

import app.db as db_module


def test_get_client_builds_from_config_and_is_cached(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    db_module.get_client.cache_clear()

    calls = []

    def fake_create_client(url, key, options=None):
        calls.append((url, key, options))
        return object()

    monkeypatch.setattr(db_module, "create_client", fake_create_client)

    first = db_module.get_client()
    second = db_module.get_client()

    assert len(calls) == 1
    url, key, _options = calls[0]
    assert (url, key) == ("https://example.supabase.co", "service-key")
    assert first is second

    db_module.get_client.cache_clear()


def test_get_client_sets_explicit_timeouts_shorter_than_supabase_py_defaults(monkeypatch):
    # T27: supabase-py's own defaults (120s postgrest, 20s storage) are far too long for a
    # citizen-facing request -- a DB hiccup must fail fast into the existing 500 path, not hang.
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    db_module.get_client.cache_clear()

    captured = {}

    def fake_create_client(url, key, options=None):
        captured["options"] = options
        return object()

    monkeypatch.setattr(db_module, "create_client", fake_create_client)

    db_module.get_client()

    options = captured["options"]
    assert options.postgrest_client_timeout == db_module.POSTGREST_TIMEOUT_SECONDS
    assert options.storage_client_timeout == db_module.STORAGE_TIMEOUT_SECONDS
    assert db_module.POSTGREST_TIMEOUT_SECONDS < 120  # supabase-py's own default
    assert db_module.STORAGE_TIMEOUT_SECONDS < 20  # supabase-py's own default

    db_module.get_client.cache_clear()
