"""T14: app/db.py's cached Supabase client factory."""

import app.db as db_module


def test_get_client_builds_from_config_and_is_cached(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    db_module.get_client.cache_clear()

    calls = []

    def fake_create_client(url, key):
        calls.append((url, key))
        return object()

    monkeypatch.setattr(db_module, "create_client", fake_create_client)

    first = db_module.get_client()
    second = db_module.get_client()

    assert calls == [("https://example.supabase.co", "service-key")]
    assert first is second

    db_module.get_client.cache_clear()
