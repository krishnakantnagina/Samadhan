"""GET /health and CORS — S01 section 6 and section 9 rules 4 and 5."""

import os

from api import HealthResponse

ALLOWED_ORIGIN = os.environ.get("CONTRACT_ALLOWED_ORIGIN", "http://localhost:3000")
BLOCKED_ORIGIN = "https://evil.example"


def test_health_is_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    HealthResponse.model_validate(response.json())


def test_allowed_origin_gets_cors_header(client):
    response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_other_origin_gets_no_cors_header(client):
    response = client.get("/health", headers={"Origin": BLOCKED_ORIGIN})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_allowed_only_for_allowed_origin(client):
    def preflight(origin):
        return client.options(
            "/api/v1/message",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )

    allowed = preflight(ALLOWED_ORIGIN)
    assert allowed.status_code == 200
    assert allowed.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert "access-control-allow-origin" not in preflight(BLOCKED_ORIGIN).headers
