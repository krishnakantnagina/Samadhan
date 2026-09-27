"""T07 app setup: /health, CORS, startup spec loading (backend/app/main.py)."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")

from app.main import create_app
from app.schemas import HealthResponse
from app.service_spec import SpecError

ALLOWED_ORIGIN = "http://localhost:3000"
BLOCKED_ORIGIN = "https://evil.example"


def test_health_is_ok():
    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        HealthResponse.model_validate(response.json())


def test_allowed_origin_gets_cors_header(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})
        assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_blocked_origin_gets_no_cors_header(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"Origin": BLOCKED_ORIGIN})
        assert "access-control-allow-origin" not in response.headers


def test_missing_allowed_origins_raises_at_creation(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        create_app()


def test_broken_spec_stops_startup(tmp_path):
    (tmp_path / "water_supply.yaml").write_text("spec_version: 1\nservice: [not, a, mapping]\n")
    with pytest.raises(SpecError), TestClient(create_app(specs_dir=tmp_path)):
        pass


def test_real_specs_load_at_startup():
    app = create_app()
    with TestClient(app):
        assert "water_supply" in app.state.specs
