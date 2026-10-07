"""Audit M11: API docs are hidden in production, and /health/ready really checks the database."""

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")

from app import db, main


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("ENV", "RAILWAY_ENVIRONMENT", "RENDER", "ENABLE_API_DOCS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")


def test_docs_are_on_in_development(clean_env):
    with TestClient(main.create_app()) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize(("name", "value"), [("RENDER", "true"), ("RAILWAY_ENVIRONMENT", "production"), ("ENV", "production")])
def test_docs_are_hidden_on_a_production_host(clean_env, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with TestClient(main.create_app()) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health").status_code == 200  # the API itself is untouched


def test_docs_can_be_switched_back_on_in_production_on_purpose(clean_env, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("ENABLE_API_DOCS", "1")
    with TestClient(main.create_app()) as client:
        assert client.get("/docs").status_code == 200


class _Offices:
    def __init__(self, fail):
        self.fail = fail

    def table(self, _):
        return self

    def select(self, *_):
        return self

    def limit(self, _):
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError("connection refused (host=db.internal password=hunter2)")
        return SimpleNamespace(data=[{"id": 1}])


def test_ready_is_ok_when_the_database_answers(clean_env, monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: _Offices(fail=False))
    with TestClient(main.create_app()) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200 and response.json() == {"status": "ok", "database": "ok"}


def test_ready_is_503_when_the_database_is_down_and_leaks_nothing(clean_env, monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: _Offices(fail=True))
    with TestClient(main.create_app()) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "down"}
    assert "hunter2" not in response.text and "db.internal" not in response.text


def test_plain_health_does_not_touch_the_database(clean_env, monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: (_ for _ in ()).throw(AssertionError("must not be called")))
    with TestClient(main.create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
