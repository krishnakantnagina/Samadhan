"""S35 understand first: Gemini translates and classifies the first message; unclear asks again; complaint goes on to Jev; the rest get the fixed replies."""

import datetime
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import intake, routes, session, turn_engine, understand
from app.service_spec import load_specs
from mock.errors import register_error_handlers

SPECS = load_specs(Path(__file__).resolve().parents[2] / "specs")


def U(kind="complaint", confidence=0.95, hindi="गाँव में मास्टर साहब स्कूल नहीं आते", english="The teacher does not come to school in our village", language="bundeli"):
    return understand.Understanding(kind, confidence, hindi, english, language)


def gemini_answer(**kw):
    body = {"language": "bundeli", "hindi": "गाँव में मास्टर साहब नहीं आते", "english": "The teacher is absent in our village", "kind": "complaint", "confidence": 0.93, **kw}
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(body, ensure_ascii=False)}]}}]}, request=httpx.Request("POST", "https://x"))


@pytest.fixture(autouse=True)
def flag_on(monkeypatch):
    monkeypatch.setenv("UNDERSTAND_FIRST", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("UNDERSTAND_MODELS", raising=False)


# --- the module ---------------------------------------------------------------------------------------------------------------------------------

def test_off_by_default_and_without_a_key(monkeypatch):
    monkeypatch.setenv("UNDERSTAND_FIRST", "")
    assert understand.enabled() is False
    monkeypatch.setenv("UNDERSTAND_FIRST", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert understand.enabled() is False
    assert understand.understand("x", post=lambda *a, **k: pytest.fail("must not call Gemini")) is None


def test_parses_a_good_answer_and_sends_key_in_a_header_and_the_message_in_the_prompt():
    seen = {}

    def post(url, headers, json, timeout):  # noqa: A002
        seen.update(url=url, headers=headers, prompt=json["contents"][0]["parts"][0]["text"], mime=json["generationConfig"]["responseMimeType"])
        return gemini_answer()

    u = understand.understand("हमारे गाँव में मारसाब नहीं आ रहा", [SimpleNamespace(role="citizen", text="पहले कुछ")], post=post)
    assert (u.kind, u.language) == ("complaint", "bundeli") and u.hindi and u.english and u.is_complaint
    assert "test-key" not in seen["url"] and seen["headers"]["x-goog-api-key"] == "test-key" and seen["mime"] == "application/json"
    assert "मारसाब" in seen["prompt"] and "पहले कुछ" in seen["prompt"]


@pytest.mark.parametrize("response", [
    httpx.Response(503, request=httpx.Request("POST", "https://x")),
    httpx.Response(200, text="not json", request=httpx.Request("POST", "https://x")),
    gemini_answer(kind="poem"),
])
def test_any_failure_returns_none_so_the_normal_pipeline_runs(response):
    assert understand.understand("कुछ", post=lambda *a, **k: response) is None


def test_default_model_chain_starts_with_gemini_model_then_the_fallbacks(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-flash")
    assert understand._models() == ["gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.1-flash-lite"]
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    assert understand._models() == ["gemini-3.1-flash-lite", "gemini-3-flash-preview"]  # no duplicate
    monkeypatch.setenv("UNDERSTAND_MODELS", "only-this")
    assert understand._models() == ["only-this"]


def test_stops_trying_models_once_the_deadline_has_passed(monkeypatch):
    monkeypatch.setenv("UNDERSTAND_MODELS", "m1,m2,m3")
    clock = iter([0.0, 0.0, 10.0, 10.0, 10.0])
    monkeypatch.setattr(understand.time, "monotonic", lambda: next(clock))
    calls = []

    def post(url, **kw):
        calls.append(url)
        return httpx.Response(503, request=httpx.Request("POST", "https://x"))

    assert understand.understand("कुछ", post=post) is None
    assert len(calls) == 1  # m1 was tried; by m2 the 9 s budget was gone


def test_tries_the_next_model_when_one_is_overloaded(monkeypatch):
    monkeypatch.setenv("UNDERSTAND_MODELS", "m1, m2")
    calls = []

    def post(url, **kw):
        calls.append(url.rsplit("/", 1)[-1])
        return httpx.Response(503, request=httpx.Request("POST", "https://x")) if "m1" in url else gemini_answer()

    assert understand.understand("कुछ", post=post).kind == "complaint"
    assert calls == ["m1:generateContent", "m2:generateContent"]


def test_low_confidence_complaint_counts_as_unclear():
    assert U("complaint", 0.3).is_unclear and not U("complaint", 0.3).is_complaint
    assert U("unclear", 0.9).is_unclear
    assert not U("question", 0.9).is_unclear and not U("greeting", 0.9).is_unclear


def test_engine_text_puts_the_translation_next_to_the_original():
    t = understand.engine_text("हमारे गाँव में मारसाब नहीं आ रहा", U())
    assert t.startswith("हमारे गाँव में मारसाब नहीं आ रहा\n(") and "मास्टर साहब" in t and "English:" in t
    assert understand.engine_text("abc", None) == "abc"


# --- the route ----------------------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    saved, seen = {}, {}
    now = datetime.datetime.now(datetime.UTC)
    state = {"collected_fields": {}}
    monkeypatch.setattr(routes.session, "get_or_create_session", lambda sid: session.Session(
        id=sid, status=session.SessionStatus.ACTIVE, service_id=None, collected_fields=state["collected_fields"], awaiting_confirmation=False,
        lat=None, lng=None, created_at=now, last_active_at=now))
    monkeypatch.setattr(routes.session, "find_stored_response", lambda sid, mid: None)
    monkeypatch.setattr(routes.session, "get_recent_messages", lambda sid, limit=4: [])
    monkeypatch.setattr(routes.session, "save_turn", lambda **kw: saved.update(kw))

    def fake_run_turn(**kw):
        seen["engine_text"] = kw["text"]
        return turn_engine.TurnResult(service_id=None, fields={}, confirmed=False, intent=seen.get("engine_intent", "complaint"))

    monkeypatch.setattr(routes.turn_engine, "run_turn", fake_run_turn)
    monkeypatch.setattr(intake.jev, "from_env", lambda: None)
    app = FastAPI()
    register_error_handlers(app)
    app.state.specs = SPECS
    app.include_router(routes.router, prefix="/api/v1")
    c = TestClient(app, raise_server_exceptions=False)
    c.saved, c.seen, c.state = saved, seen, state
    return c


def send(client, text="हमारे गाँव में मारसाब नहीं आ रहा"):
    return client.post("/api/v1/message", files={"session_id": (None, str(uuid.uuid4())), "message_id": (None, str(uuid.uuid4())), "text": (None, text)})


def test_unclear_asks_for_the_complaint_again_without_running_the_engine(client, monkeypatch):
    monkeypatch.setattr(understand, "understand", lambda text, recent=(), **kw: U("unclear", 0.9, "", ""))
    monkeypatch.setattr(routes.turn_engine, "run_turn", lambda **kw: pytest.fail("the engine must not run for an unclear message"))
    body = send(client, "mujhe problem hai").json()
    assert body["action"] == "ask" and body["ask_for"] == "complaint" and body["reply_text"] == understand.ASK_AGAIN_HI
    assert client.saved["session_update"].collected_fields[understand.META_KEY]["asked"] == 1


def test_after_two_asks_the_normal_pipeline_takes_the_message(client, monkeypatch):
    monkeypatch.setattr(understand, "understand", lambda text, recent=(), **kw: U("unclear", 0.9, "", ""))
    client.state["collected_fields"] = {understand.META_KEY: {"asked": 2}}
    body = send(client, "mujhe problem hai").json()
    assert body["ask_for"] != "complaint"  # no third "tell me again": the engine and validator handle it (here: no service, so they ask which one)


def test_complaint_reaches_the_engine_with_the_translation_and_jev_reads_it_too(client, monkeypatch):
    monkeypatch.setattr(understand, "understand", lambda text, recent=(), **kw: U())
    states = []

    class Jev:
        def decide(self, state, departments):
            states.append(state["citizen_message"])
            return intake.jev.DeptDecision((("school_education", 0.97), ("phe", 0.02)), 0.97, 0.0)

        def agrees(self, state, statement):
            return 1.0

    monkeypatch.setattr(intake, "default_decider", lambda: Jev())
    monkeypatch.setenv("INTAKE_V2", "1")
    body = send(client).json()
    assert "मानक हिंदी: गाँव में मास्टर साहब" in client.seen["engine_text"]
    assert states and "मास्टर साहब" in states[0]  # Jev got the plain-language version, not just "मारसाब"
    assert client.saved["session_update"].service_id == "school_education"
    meta = client.saved["session_update"].collected_fields[intake.META_KEY]
    assert meta[understand.META_KEY]["kind"] == "complaint" and meta[understand.META_KEY]["english"]
    assert body["action"] == "ask"  # the next question (where?), not a ticket yet


@pytest.mark.parametrize("kind", ["question", "document_request"])
def test_question_and_document_request_get_the_information_reply_not_a_ticket(client, monkeypatch, kind):
    monkeypatch.setattr(understand, "understand", lambda text, recent=(), **kw: U(kind, 0.9, "जाति प्रमाण पत्र कैसे बनता है", "How is a caste certificate made"))
    body = send(client, "jati praman patra kaise banta hai").json()
    assert body["action"] == "out_of_scope" and body["ticket"] is None
    assert "आधिकारिक" in body["reply_text"]  # the fixed information message


def test_greeting_gets_the_out_of_context_reply(client, monkeypatch):
    monkeypatch.setattr(understand, "understand", lambda text, recent=(), **kw: U("greeting", 0.95, "नमस्ते", "Hello"))
    body = send(client, "namaste").json()
    assert body["action"] == "out_of_scope" and "शिकायत" in body["reply_text"]


def test_engine_calling_it_information_but_gemini_saying_complaint_wins(client, monkeypatch):
    client.seen["engine_intent"] = "information"
    monkeypatch.setattr(understand, "understand", lambda text, recent=(), **kw: U())
    body = send(client).json()
    assert body["action"] == "ask" and body["ask_for"] != "complaint" and body["ticket"] is None  # treated as a complaint: it goes on to ask what is missing


def test_gemini_down_changes_nothing(client, monkeypatch):
    monkeypatch.setattr(understand, "understand", lambda text, recent=(), **kw: None)
    send(client)
    assert client.seen["engine_text"] == "हमारे गाँव में मारसाब नहीं आ रहा"  # exactly the citizen's words


def test_not_run_in_the_middle_of_a_complaint(client, monkeypatch):
    monkeypatch.setattr(routes.session, "get_or_create_session", lambda sid: session.Session(
        id=sid, status=session.SessionStatus.ACTIVE, service_id="water_supply", collected_fields={}, awaiting_confirmation=False, lat=None, lng=None,
        created_at=datetime.datetime.now(datetime.UTC), last_active_at=datetime.datetime.now(datetime.UTC)))
    monkeypatch.setattr(understand, "understand", lambda *a, **k: pytest.fail("an answer like 'Misrod' must not be re-classified"))
    send(client, "Misrod")
