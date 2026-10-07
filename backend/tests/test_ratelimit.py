"""Rate limits (audit H4): the window maths, the limits per route, and that a refusal is the 429 the website already understands."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth_routes, ratelimit, routes
from app import schemas as api
from mock.errors import register_error_handlers


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_window_allows_the_limit_then_refuses_with_a_wait_time():
    clock = Clock()
    window = ratelimit.SlidingWindow(clock)
    assert all(window.hit("ip1", 3)[0] for _ in range(3))
    allowed, wait = window.hit("ip1", 3)
    assert not allowed and 1 <= wait <= 61


def test_window_frees_up_as_old_requests_age_out():
    clock = Clock()
    window = ratelimit.SlidingWindow(clock)
    for _ in range(3):
        window.hit("ip1", 3)
    clock.now += 61
    assert window.hit("ip1", 3)[0]


def test_keys_do_not_share_a_budget():
    window = ratelimit.SlidingWindow(Clock())
    for _ in range(3):
        window.hit("ip1", 3)
    assert not window.hit("ip1", 3)[0]
    assert window.hit("ip2", 3)[0]


def test_idle_keys_are_dropped_so_memory_stays_bounded(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(ratelimit, "MAX_KEYS", 10)
    window = ratelimit.SlidingWindow(clock)
    for i in range(8):
        window.hit(f"old{i}", 5)
    clock.now += 120
    for i in range(8):
        window.hit(f"new{i}", 5)
    assert len(window._hits) <= 10


@pytest.fixture
def limited(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)
    ratelimit.reset()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(routes.router, prefix="/api/v1")
    app.include_router(auth_routes.router, prefix="/api/v1")
    yield TestClient(app)
    ratelimit.reset()


def test_speak_is_limited_per_address_and_the_refusal_is_the_known_429(limited, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_SPEAK", "3")
    monkeypatch.setattr(routes.tts, "synthesize", lambda text: "AAAA")
    codes = [limited.post("/api/v1/speak", json={"text": "नमस्ते"}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    body = limited.post("/api/v1/speak", json={"text": "नमस्ते"}).json()
    assert body["error_code"] == "RATE_LIMITED" and body["reply_text"] == api.ERROR_REPLY_TEXT[api.ErrorCode.RATE_LIMITED]


def test_a_refused_speak_request_never_reaches_the_paid_provider(limited, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_SPEAK", "1")
    calls = []
    monkeypatch.setattr(routes.tts, "synthesize", lambda text: calls.append(text) or "AAAA")
    for _ in range(4):
        limited.post("/api/v1/speak", json={"text": "नमस्ते"})
    assert len(calls) == 1


def test_message_is_limited_per_session_even_from_different_addresses(limited, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_MESSAGE_SESSION", "2")
    monkeypatch.setenv("RATE_LIMIT_MESSAGE", "0")  # per-IP off: only the session limit is under test
    session = str(uuid.uuid4())
    statuses = []
    for _ in range(4):
        r = limited.post("/api/v1/message", data={"session_id": session, "message_id": str(uuid.uuid4())})  # no text: a 400 BEFORE any work, which is fine
        statuses.append(r.status_code)
    assert statuses[:2] == [400, 400] and statuses[2:] == [429, 429]
    other = limited.post("/api/v1/message", data={"session_id": str(uuid.uuid4()), "message_id": str(uuid.uuid4())})
    assert other.status_code == 400  # a different session is untouched


def test_auth_start_is_limited(limited, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_AUTH_START", "2")
    codes = [limited.post("/api/v1/auth/start", json={"phone": "9876543210"}).status_code for _ in range(3)]
    assert codes[2] == 429


def test_zero_turns_a_limit_off_and_the_disable_switch_turns_all_off(limited, monkeypatch):
    monkeypatch.setattr(routes.tts, "synthesize", lambda text: "AAAA")
    monkeypatch.setenv("RATE_LIMIT_SPEAK", "0")
    assert all(limited.post("/api/v1/speak", json={"text": "x"}).status_code == 200 for _ in range(5))
    monkeypatch.setenv("RATE_LIMIT_SPEAK", "1")
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")
    ratelimit.reset()
    assert all(limited.post("/api/v1/speak", json={"text": "x"}).status_code == 200 for _ in range(5))


def test_forwarded_for_is_used_only_when_trusted(monkeypatch):
    from types import SimpleNamespace

    request = SimpleNamespace(headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, client=SimpleNamespace(host="10.0.0.1"))

    monkeypatch.delenv("TRUST_FORWARDED_FOR", raising=False)
    assert ratelimit.client_ip(request) == "10.0.0.1"
    monkeypatch.setenv("TRUST_FORWARDED_FOR", "1")
    assert ratelimit.client_ip(request) == "203.0.113.7"


def test_bad_limit_values_fall_back_to_the_default(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_SPEAK", "lots")
    assert ratelimit.limit_for("speak") == ratelimit.DEFAULTS["speak"]
