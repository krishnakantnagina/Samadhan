"""Contract test wiring.

The same suite runs against the mock (default, in-process) or a live server:

    uv run pytest                                            # mock, in-process
    BASE_URL=http://localhost:8000 uv run pytest             # a running mock, over HTTP
    BASE_URL=... CONTRACT_TARGET=real uv run pytest          # the real backend

Tests marked `mock_only` need the mock's deterministic triggers and are skipped when
CONTRACT_TARGET=real. Other env vars: CONTRACT_EXISTING_ID (a ticket that exists),
CONTRACT_ALLOWED_ORIGIN (an origin in ALLOWED_ORIGINS).
"""

import os

import httpx
import pytest

os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")

TARGET = os.environ.get("CONTRACT_TARGET", "mock")
BASE_URL = os.environ.get("BASE_URL")


def pytest_collection_modifyitems(config, items):
    if TARGET != "real":
        return
    skip = pytest.mark.skip(reason="mock_only: needs the mock's deterministic triggers")
    for item in items:
        if "mock_only" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def client():
    if BASE_URL:
        with httpx.Client(base_url=BASE_URL, timeout=30) as http:
            yield http
        return

    from fastapi.testclient import TestClient

    if TARGET == "real":
        # T18: needs real .env credentials (Groq/Gemini/Supabase) -- nothing is mocked here.
        from app.main import app
    else:
        from mock.app import app

    with TestClient(app, raise_server_exceptions=False) as http:
        yield http
