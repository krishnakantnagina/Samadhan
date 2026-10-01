"""S31 registration and saved login: provider, service, stores, endpoints, and the 'log in before filing a complaint' gate."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, auth_routes, routes, schemas, session, turn_engine, validator
from mock.errors import register_error_handlers

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


def make_service(**kw):
    clock = Clock()
    service = auth.AuthService(auth.MemoryAuthStore(now=clock), auth.DemoProvider(), now=clock, **kw)
    return service, clock


def login(service, phone="98765 43210", pin="5555"):
    return service.verify(service.start(phone).challenge_id, pin)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("AUTH_PROVIDER", "AUTH_REQUIRED", "RAILWAY_ENVIRONMENT", "RENDER", "AUTH_DEMO_IN_PRODUCTION", "AUTH_IDLE_DAYS", "AUTH_MAX_DAYS"):
        monkeypatch.delenv(name, raising=False)
    auth.get_service.cache_clear()
    yield
    getattr(auth.get_service, "cache_clear", lambda: None)()  # a test may have replaced get_service with a plain function


# --- phone numbers -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["9876543210", "98765 43210", "+91 98765-43210", "09876543210", "919876543210", "(98765) 43210"])
def test_phone_numbers_are_normalised(raw):
    assert auth.normalise_phone(raw) == "+919876543210"


@pytest.mark.parametrize("raw", ["", "12345", "98765432101234", "abcdefghij", "+1 415 555 0100"])
def test_bad_phone_numbers_are_rejected(raw):
    with pytest.raises(auth.AuthError) as e:
        auth.normalise_phone(raw)
    assert e.value.code is schemas.ErrorCode.INVALID_INPUT


def test_masking_hides_the_middle_of_the_number():
    assert auth.mask_phone("+919876543210") == "+91 ••••••3210"
    assert "98765" not in auth.mask_phone("+919876543210")


# --- the demo provider and the login service ----------------------------------------------------------------------

def test_demo_provider_accepts_only_the_fixed_pin():
    p = auth.DemoProvider()
    assert p.verify("+919876543210", "5555").verified_by == "demo" and p.verify("+919876543210", "1234") is None and "5555" in p.hint


def test_start_then_verify_logs_in_and_the_same_phone_is_the_same_user():
    service, _ = make_service()
    first, second = login(service), login(service, phone="+91 98765 43210")
    assert first.user.id == second.user.id and first.user.phone == "+919876543210" and first.token != second.token
    assert service.user_for_token(first.token).id == first.user.id


def test_the_token_is_never_stored_only_its_hash():
    service, _ = make_service()
    result = login(service)
    assert result.token not in service.store.sessions and auth.hash_token(result.token) in service.store.sessions


def test_a_wrong_pin_is_rejected_and_attempts_are_limited():
    service, _ = make_service(max_attempts=3)
    cid = service.start("9876543210").challenge_id
    for _ in range(3):
        with pytest.raises(auth.AuthError) as e:
            service.verify(cid, "0000")
        assert e.value.code is schemas.ErrorCode.AUTH_INVALID_CODE
    with pytest.raises(auth.AuthError) as e:  # locked out: even the right PIN no longer works on this challenge
        service.verify(cid, "5555")
    assert e.value.code is schemas.ErrorCode.AUTH_RATE_LIMITED
    with pytest.raises(auth.AuthError) as e:
        service.verify(cid, "5555")
    assert e.value.code is schemas.ErrorCode.AUTH_INVALID_CODE  # the challenge is gone: start again


def test_starting_too_often_is_rate_limited_per_phone_per_hour():
    service, clock = make_service(max_starts_per_hour=3)
    for _ in range(3):
        service.start("9876543210")
    with pytest.raises(auth.AuthError) as e:
        service.start("9876543210")
    assert e.value.code is schemas.ErrorCode.AUTH_RATE_LIMITED
    service.start("9123456789")  # another phone is unaffected
    clock.advance(hours=1, minutes=1)
    service.start("9876543210")


def test_an_expired_or_unknown_challenge_cannot_be_verified():
    service, clock = make_service(challenge_minutes=10)
    cid = service.start("9876543210").challenge_id
    clock.advance(minutes=11)
    for challenge in (cid, "00000000-0000-4000-8000-00000000dead"):
        with pytest.raises(auth.AuthError) as e:
            service.verify(challenge, "5555")
        assert e.value.code is schemas.ErrorCode.AUTH_INVALID_CODE


# --- saved login: sliding expiry, absolute maximum, logout ----------------------------------------------------------

def test_the_login_stays_alive_while_it_is_used_and_expires_when_idle():
    service, clock = make_service(idle_days=30, max_days=90)
    token = login(service).token
    clock.advance(days=20)
    assert service.user_for_token(token) is not None  # used on day 20: the idle window moves
    clock.advance(days=20)
    assert service.user_for_token(token) is not None  # day 40 is 20 idle days after day 20
    clock.advance(days=31)
    assert service.user_for_token(token) is None  # 31 idle days: log in again


def test_even_a_daily_user_must_log_in_again_after_the_absolute_maximum():
    service, clock = make_service(idle_days=30, max_days=90)
    token = login(service).token
    for _ in range(89):
        clock.advance(days=1)
        assert service.user_for_token(token) is not None
    clock.advance(days=2)
    assert service.user_for_token(token) is None
    assert service.expires_at(token) <= T0 + timedelta(days=90)  # the idle window never reaches past the absolute limit


def test_logout_revokes_the_token_and_unknown_tokens_are_not_users():
    service, _ = make_service()
    token = login(service).token
    service.logout(token)
    assert service.user_for_token(token) is None
    assert service.user_for_token("nonsense") is None and service.user_for_token(None) is None and service.user_for_token("") is None
    service.logout(None)
    service.logout("nonsense")  # harmless


def test_whatsapp_or_call_identities_need_no_pin_and_share_the_same_user_table():
    service, _ = make_service()
    via_pin = login(service).user
    via_whatsapp = service.user_for_channel("+91 98765 43210", "whatsapp")
    assert via_whatsapp.id == via_pin.id
    fresh = service.user_for_channel("9123456789", "caller_id")
    assert fresh.verified_by == "caller_id" and fresh.phone == "+919123456789"


# --- configuration --------------------------------------------------------------------------------------------------

def test_auth_is_off_unless_a_provider_is_configured():
    with pytest.raises(auth.AuthDisabled):
        auth.get_service()
    assert auth.required() is False and auth.user_from_header("Bearer anything") is None


def test_required_needs_both_the_switch_and_a_provider(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    assert auth.required() is False  # no provider: fail open, complaints are never blocked by a setup mistake
    monkeypatch.setenv("AUTH_PROVIDER", "demo")
    assert auth.required() is True


def test_unknown_provider_and_the_demo_pin_in_production_are_refused(monkeypatch):
    monkeypatch.setenv("AUTH_PROVIDER", "carrier-pigeon")
    with pytest.raises(auth.AuthDisabled):
        auth.get_service()
    auth.get_service.cache_clear()
    monkeypatch.setenv("AUTH_PROVIDER", "demo")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    with pytest.raises(auth.AuthDisabled, match="production"):
        auth.get_service()
    auth.get_service.cache_clear()
    monkeypatch.setenv("AUTH_DEMO_IN_PRODUCTION", "1")  # only on purpose
    monkeypatch.setattr("app.db.get_client", lambda: (_ for _ in ()).throw(RuntimeError("no database in tests")))
    assert isinstance(auth.get_service().provider, auth.DemoProvider)


@pytest.mark.parametrize("header, token", [("Bearer abc", "abc"), ("bearer  abc ", "abc"), ("Basic abc", None), ("Bearer", None), ("", None), (None, None)])
def test_bearer_header_parsing(header, token):
    assert auth.token_from_header(header) == token


# --- the Supabase store against a fake database ------------------------------------------------------------------------

class FakeTable:
    def __init__(self, db, name, now):
        self.db, self.name, self.now, self.filters, self.op, self.payload, self.count = db, name, now, [], "select", None, None

    def select(self, cols="*", count=None):
        self.op, self.count = "select", count
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, value):
        self.filters.append(("eq", col, value))
        return self

    def gte(self, col, value):
        self.filters.append(("gte", col, value))
        return self

    def execute(self):
        rows = self.db.setdefault(self.name, [])
        if self.op == "insert":
            row = {"id": str(uuid.uuid4()), "created_at": self.now().isoformat(), "attempts": 0, "revoked": False, **self.payload}
            rows.append(row)
            return SimpleNamespace(data=[row], count=None)
        hit = [r for r in rows if all((r.get(c) == v) if op == "eq" else (str(r.get(c)) >= str(v)) for op, c, v in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
        elif self.op == "delete":
            self.db[self.name] = [r for r in rows if r not in hit]
        return SimpleNamespace(data=hit, count=len(hit) if self.count else None)


class FakeSupabase:
    def __init__(self, now=lambda: datetime.now(UTC)):
        self.db, self.now = {}, now

    def table(self, name):
        return FakeTable(self.db, name, self.now)


def test_the_supabase_store_supports_the_whole_login_lifecycle():
    clock = Clock()
    client = FakeSupabase(now=clock)
    service = auth.AuthService(auth.SupabaseAuthStore(client), auth.DemoProvider(), now=clock, max_attempts=2, max_starts_per_hour=3)
    result = login(service)
    again = login(service)
    assert len(client.db["users"]) == 1 and result.user.id == again.user.id  # one user per phone
    assert all(auth.hash_token(t) in {s["token_hash"] for s in client.db["auth_sessions"]} for t in (result.token, again.token))
    assert result.token not in str(client.db)  # the raw token is nowhere in the database
    assert service.user_for_token(result.token).phone == "+919876543210"
    clock.advance(days=31)
    assert service.user_for_token(result.token) is None  # idle expiry works through ISO strings from the database
    cid = service.start("9123456789").challenge_id
    with pytest.raises(auth.AuthError):
        service.verify(cid, "0000")
    assert client.db["auth_challenges"][-1]["attempts"] == 1
    service.start("9123456789")
    service.start("9123456789")  # 3 started so far for this phone (the limit is 3 per hour)
    with pytest.raises(auth.AuthError) as limited:
        service.start("9123456789")
    assert limited.value.code is schemas.ErrorCode.AUTH_RATE_LIMITED  # the hourly limit counts rows in the database


# --- endpoints ---------------------------------------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch):
    service, clock = make_service()
    monkeypatch.setattr(auth, "get_service", lambda: service)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(auth_routes.router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)
    client.service, client.clock = service, clock
    return client


def start_and_verify(client, phone="98765 43210", pin="5555"):
    started = client.post("/api/v1/auth/start", json={"phone": phone})
    assert started.status_code == 200, started.text
    return client.post("/api/v1/auth/verify", json={"challenge_id": started.json()["challenge_id"], "code": pin})


def test_login_flow_over_http(api):
    started = api.post("/api/v1/auth/start", json={"phone": "98765 43210"}).json()
    assert started["provider"] == "demo" and "5555" in started["hint"]
    verified = api.post("/api/v1/auth/verify", json={"challenge_id": started["challenge_id"], "code": "5555"}).json()
    assert verified["phone_masked"] == "+91 ••••••3210" and "9876543210" not in str(verified) and len(verified["token"]) > 30
    me = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {verified['token']}"})
    assert me.status_code == 200 and me.json()["phone_masked"] == "+91 ••••••3210"
    assert api.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {verified['token']}"}).status_code == 200
    again = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {verified['token']}"})
    assert again.status_code == 401 and again.json()["error_code"] == "AUTH_EXPIRED" and again.json()["reply_text"]


def test_errors_carry_the_contract_codes_and_citizen_safe_text(api):
    assert api.get("/api/v1/auth/me").json()["error_code"] == "AUTH_REQUIRED"
    wrong = start_and_verify(api, pin="0000")
    assert wrong.status_code == 401 and wrong.json()["error_code"] == "AUTH_INVALID_CODE" and "कोड" in wrong.json()["reply_text"]
    assert api.post("/api/v1/auth/start", json={"phone": "123"}).status_code == 400
    assert "5555" not in wrong.text  # the PIN is never echoed back
    for _ in range(5):
        api.post("/api/v1/auth/start", json={"phone": "98700 00000"})
    limited = api.post("/api/v1/auth/start", json={"phone": "98700 00000"})
    assert limited.status_code == 429 and limited.json()["error_code"] == "AUTH_RATE_LIMITED"


def test_every_login_endpoint_answers_503_when_auth_is_not_configured(monkeypatch):
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(auth_routes.router, prefix="/api/v1")
    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/api/v1/auth/start", json={"phone": "9876543210"}).status_code == 503
    assert c.post("/api/v1/auth/verify", json={"challenge_id": "x" * 10, "code": "5555"}).status_code == 503
    assert c.get("/api/v1/auth/me", headers={"Authorization": "Bearer t"}).status_code == 503


# --- the gate: a complaint needs login; an enquiry does not --------------------------------------------------------------

SPEC_OK = validator.ValidationResult(service_id="water_supply", collected_fields={"issue_type": "no_supply", "location": "किलोजा"}, awaiting_confirmation=False,
                                     action=validator.ValidatedAction.READY_TO_SUBMIT, ask_for=None, reply_text=None, summary={"issue": "No water"})


@pytest.fixture
def chat(monkeypatch):
    saved, tickets = {}, []
    now = datetime.now(UTC)
    monkeypatch.setattr(routes.session, "get_or_create_session", lambda sid: session.Session(
        id=sid, status=session.SessionStatus.ACTIVE, service_id="water_supply", collected_fields={"issue_type": "no_supply"}, awaiting_confirmation=True,
        lat=None, lng=None, created_at=now, last_active_at=now))
    monkeypatch.setattr(routes.session, "find_stored_response", lambda sid, mid: None)
    monkeypatch.setattr(routes.session, "get_recent_messages", lambda sid, limit=4: [])
    monkeypatch.setattr(routes.session, "save_turn", lambda **kw: saved.update(kw))
    monkeypatch.setattr(routes.turn_engine, "run_turn", lambda **kw: turn_engine.TurnResult(service_id="water_supply", fields={}, confirmed=True))
    monkeypatch.setattr(routes.validator, "apply", lambda **kw: SPEC_OK)
    monkeypatch.setattr(routes.ticketing, "create_ticket", lambda **kw: tickets.append(kw) or schemas.Ticket(
        complaint_id="SMD-0042", department="Jal Vibhag", office=schemas.Office(name="x", level="district"), status="new"))
    monkeypatch.setattr(routes.intake, "enabled", lambda: False)
    app = FastAPI()
    register_error_handlers(app)
    app.state.specs = {"water_supply": SimpleNamespace(service="water_supply", department="Jal Vibhag")}
    app.include_router(routes.router, prefix="/api/v1")
    c = TestClient(app, raise_server_exceptions=False)
    c.saved, c.tickets = saved, tickets
    return c


def say(client, headers=None, text="हाँ"):
    return client.post("/api/v1/message", files={"session_id": (None, str(uuid.uuid4())), "message_id": (None, str(uuid.uuid4())), "text": (None, text)}, headers=headers or {})


def test_filing_a_complaint_without_login_asks_to_log_in_and_keeps_the_draft(chat, monkeypatch):
    monkeypatch.setattr(auth, "required", lambda: True)
    monkeypatch.setattr(auth, "user_from_header", lambda header: None)
    body = say(chat).json()
    assert body["action"] == "ask" and body["ask_for"] == "login" and "मोबाइल" in body["reply_text"] and body["ticket"] is None
    assert chat.tickets == []  # nothing filed
    saved = chat.saved["session_update"]
    assert saved.awaiting_confirmation is True and saved.service_id == "water_supply" and saved.collected_fields["issue_type"] == "no_supply"  # the draft survives the login


def test_after_login_the_same_confirmation_files_the_ticket_for_that_user(chat, monkeypatch):
    monkeypatch.setattr(auth, "required", lambda: True)
    monkeypatch.setattr(auth, "user_from_header", lambda header: auth.User("user-1", "+919876543210", "demo") if header == "Bearer good" else None)
    body = say(chat, headers={"Authorization": "Bearer good"}).json()
    assert body["action"] == "submitted" and body["ticket"]["complaint_id"] == "SMD-0042"
    assert chat.tickets[0]["user_id"] == "user-1"


def test_without_the_switch_complaints_are_filed_as_before(chat, monkeypatch):
    monkeypatch.setattr(auth, "required", lambda: False)
    assert say(chat).json()["action"] == "submitted" and chat.tickets[0]["user_id"] is None


def test_a_logged_in_citizen_is_linked_even_when_registration_is_not_required(chat, monkeypatch):
    monkeypatch.setattr(auth, "required", lambda: False)
    monkeypatch.setattr(auth, "user_from_header", lambda header: auth.User("user-9", "+919876543210", "demo"))
    say(chat, headers={"Authorization": "Bearer t"})
    assert chat.tickets[0]["user_id"] == "user-9"


def test_cors_allows_the_authorization_header(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost")  # app.main builds the app on import, so this must come first
    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    r = client.options("/api/v1/message", headers={"Origin": "http://localhost", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"})
    assert r.status_code == 200 and "authorization" in r.headers.get("access-control-allow-headers", "").lower()


def test_demo_provider_refused_on_render(monkeypatch):
    monkeypatch.setenv("AUTH_PROVIDER", "demo")
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(auth.AuthDisabled):
        auth.get_service()
    monkeypatch.setenv("AUTH_DEMO_IN_PRODUCTION", "1")
    auth.get_service.cache_clear()
    assert auth.get_service() is not None
