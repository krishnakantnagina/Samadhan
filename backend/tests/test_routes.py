"""T18 POST /message orchestration: right calls, right order, right error mapping. Every
collaborator (session/turn_engine/validator/ticketing) is already fully tested on its own -- these
tests only check that routes.py wires them together correctly, via monkeypatching.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import routes, session, turn_engine, validator, voice
from app import schemas as api
from app.service_spec import ServiceSpec
from mock.errors import register_error_handlers

SPEC = ServiceSpec.model_validate(
    {
        "spec_version": 1,
        "service": "water_supply",
        "department": "Jal Vibhag",
        "label": {"hi": "पानी", "en": "Water"},
        "recognise": ["no water"],
        "out_of_scope": {"examples": ["electricity"], "reply": {"hi": "क्षमा करें", "en": "Sorry"}},
        "pilot": {"city": "Bhopal", "wards": 5},
        "routing": {
            "min_confidence": 0.7,
            "fallback_level": "district",
            "fallback_status": "needs_review",
            "max_match_distance_km": 5,
        },
        "confirmation": "required",
        "fields": [
            {
                "name": "issue_type",
                "type": "enum",
                "required": True,
                "label": {"hi": "समस्या", "en": "Issue"},
                "question": {"hi": "समस्या?", "en": "Problem?"},
                "values": [
                    {"value": "no_supply", "hi": "पानी नहीं", "en": "No water"},
                    {"value": "leakage", "hi": "लीकेज", "en": "Leakage"},
                ],
            },
            {
                "name": "location",
                "type": "location",
                "required": True,
                "label": {"hi": "स्थान", "en": "Location"},
                "question": {"hi": "स्थान?", "en": "Where?"},
                "accepts": {
                    "gps": {"lat": [-90, 90], "lng": [-180, 180]},
                    "place_name": {"min_length": 2, "max_length": 100},
                },
            },
        ],
    }
)


def make_session_row(**overrides) -> session.Session:
    from datetime import UTC, datetime

    base = {
        "id": uuid.uuid4(),
        "status": session.SessionStatus.ACTIVE,
        "service_id": None,
        "collected_fields": {},
        "awaiting_confirmation": False,
        "lat": None,
        "lng": None,
        "created_at": datetime.now(UTC),
        "last_active_at": datetime.now(UTC),
    }
    base.update(overrides)
    return session.Session(**base)


def raise_if_called(*_args, **_kwargs):
    raise AssertionError("must not be called")


@pytest.fixture
def test_client(monkeypatch):
    monkeypatch.setattr(
        routes.session, "get_or_create_session", lambda sid: make_session_row(id=sid)
    )
    monkeypatch.setattr(routes.session, "find_stored_response", lambda sid, mid: None)
    monkeypatch.setattr(routes.session, "get_recent_messages", lambda sid, limit=4: [])
    monkeypatch.setattr(routes.session, "save_turn", lambda **kwargs: None)

    app = FastAPI()
    register_error_handlers(app)
    app.state.specs = {SPEC.service: SPEC}
    app.include_router(routes.router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


def post(client, **fields):
    fields.setdefault("session_id", str(uuid.uuid4()))
    fields.setdefault("message_id", str(uuid.uuid4()))
    data = {k: str(v) for k, v in fields.items() if k != "audio"}
    files = {k: (None, v) for k, v in data.items()}
    if "audio" in fields:
        files["audio"] = ("voice.webm", fields["audio"], "audio/webm")
    return client.post("/api/v1/message", files=files)


# --- Audio (T26, S12) -----------------------------------------------------------------------


def test_audio_transcribed_and_fed_to_turn_engine(test_client, monkeypatch):
    monkeypatch.setattr(
        routes.voice,
        "transcribe",
        lambda *args, **kwargs: voice.VoiceResult(
            transcript="paani nahi aa raha", audio_path="sid/mid.webm"
        ),
    )
    captured = {}

    def fake_run_turn(**kwargs):
        captured.update(kwargs)
        return turn_engine.TurnResult(service_id="water_supply", fields={}, confirmed=False)

    monkeypatch.setattr(routes.turn_engine, "run_turn", fake_run_turn)
    monkeypatch.setattr(
        routes.validator,
        "apply",
        lambda **kwargs: validator.ValidationResult(
            service_id="water_supply",
            collected_fields={},
            awaiting_confirmation=False,
            action=validator.ValidatedAction.ASK,
            ask_for="issue_type",
            reply_text="समस्या?",
            summary=None,
        ),
    )
    saved = {}
    monkeypatch.setattr(routes.session, "save_turn", lambda **kwargs: saved.update(kwargs))

    response = post(test_client, audio=b"\x1aE\xdf\xa3fake-audio")

    assert response.status_code == 200
    assert captured["text"] == "paani nahi aa raha"
    assert response.json()["transcript"] == "paani nahi aa raha"
    assert saved["audio_path"] == "sid/mid.webm"
    assert saved["input_type"] == session.InputType.AUDIO


def test_empty_transcript_returns_action_error(test_client, monkeypatch):
    monkeypatch.setattr(
        routes.voice,
        "transcribe",
        lambda *args, **kwargs: voice.VoiceResult(transcript="", audio_path="sid/mid.webm"),
    )
    monkeypatch.setattr(routes.turn_engine, "run_turn", raise_if_called)
    saved = {}
    monkeypatch.setattr(routes.session, "save_turn", lambda **kwargs: saved.update(kwargs))

    response = post(test_client, audio=b"\x1aE\xdf\xa3fake-audio")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "error"
    assert body["transcript"] == ""
    assert saved["audio_path"] == "sid/mid.webm"


def test_voice_unavailable_is_503(test_client, monkeypatch):
    def raise_unavailable(*args, **kwargs):
        raise voice.VoiceUnavailable("both ASR providers failed")

    monkeypatch.setattr(routes.voice, "transcribe", raise_unavailable)

    response = post(test_client, audio=b"\x1aE\xdf\xa3fake-audio")

    assert response.status_code == 503
    assert response.json()["error_code"] == "SERVICE_UNAVAILABLE"


def test_unsupported_audio_type_is_415(test_client):
    response = test_client.post(
        "/api/v1/message",
        files={
            "session_id": (None, str(uuid.uuid4())),
            "message_id": (None, str(uuid.uuid4())),
            "audio": ("voice.mp3", b"fake", "audio/mpeg"),
        },
    )
    assert response.status_code == 415


def test_oversized_audio_is_413(test_client):
    big = b"0" * (api.AUDIO_MAX_BYTES + 1)
    response = test_client.post(
        "/api/v1/message",
        files={
            "session_id": (None, str(uuid.uuid4())),
            "message_id": (None, str(uuid.uuid4())),
            "audio": ("voice.webm", big, "audio/webm"),
        },
    )
    assert response.status_code == 413


# --- Dedupe ------------------------------------------------------------------------------------


def test_duplicate_message_id_short_circuits(test_client, monkeypatch):
    session_id, message_id = str(uuid.uuid4()), str(uuid.uuid4())
    canned = api.MessageResponse(
        session_id=session_id,
        message_id=message_id,
        action=api.Action.ASK,
        ask_for="location",
        reply_text="stored reply",
        transcript=None,
        summary=None,
        ticket=None,
        duplicate=False,
    )
    monkeypatch.setattr(routes.session, "find_stored_response", lambda sid, mid: canned)
    monkeypatch.setattr(routes.session, "get_or_create_session", raise_if_called)
    monkeypatch.setattr(routes.turn_engine, "run_turn", raise_if_called)
    monkeypatch.setattr(routes.session, "save_turn", raise_if_called)

    response = post(test_client, session_id=session_id, message_id=message_id, text="hi")

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is True
    assert body["reply_text"] == "stored reply"


# --- Commands (never reach the Turn Engine) -------------------------------------------------


def test_cancel_never_reaches_turn_engine(test_client, monkeypatch):
    monkeypatch.setattr(routes.turn_engine, "run_turn", raise_if_called)
    saved = {}
    monkeypatch.setattr(routes.session, "save_turn", lambda **kwargs: saved.update(kwargs))

    response = post(test_client, text="cancel")

    assert response.status_code == 200
    assert response.json()["action"] == "cancelled"
    update = saved["session_update"]
    assert update.status == session.SessionStatus.CANCELLED
    assert update.collected_fields == {}
    assert update.awaiting_confirmation is False


def test_restart_clears_lat_lng_too(test_client, monkeypatch):
    monkeypatch.setattr(routes.turn_engine, "run_turn", raise_if_called)
    saved = {}
    monkeypatch.setattr(routes.session, "save_turn", lambda **kwargs: saved.update(kwargs))

    response = post(test_client, text="restart")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "ask"
    assert body["ask_for"] is None
    update = saved["session_update"]
    assert update.lat is None
    assert update.lng is None
    assert update.collected_fields == {}


# --- Turn Engine + Validator wiring ----------------------------------------------------------


def test_ask_flow_returns_200_with_ask_for(test_client, monkeypatch):
    monkeypatch.setattr(
        routes.turn_engine,
        "run_turn",
        lambda **kwargs: turn_engine.TurnResult(
            service_id="water_supply", fields={"issue_type": "no_supply"}, confirmed=False
        ),
    )
    monkeypatch.setattr(
        routes.validator,
        "apply",
        lambda **kwargs: validator.ValidationResult(
            service_id="water_supply",
            collected_fields={"issue_type": "no_supply"},
            awaiting_confirmation=False,
            action=validator.ValidatedAction.ASK,
            ask_for="location",
            reply_text="स्थान?",
            summary=None,
        ),
    )

    response = post(test_client, text="paani nahi aa raha")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "ask"
    assert body["ask_for"] == "location"
    assert body["reply_text"] == "स्थान?"


def test_ready_to_submit_creates_ticket_and_clears_session(test_client, monkeypatch):
    monkeypatch.setattr(
        routes.turn_engine,
        "run_turn",
        lambda **kwargs: turn_engine.TurnResult(
            service_id="water_supply", fields={}, confirmed=True
        ),
    )
    monkeypatch.setattr(
        routes.validator,
        "apply",
        lambda **kwargs: validator.ValidationResult(
            service_id="water_supply",
            collected_fields={"issue_type": "no_supply", "location": "Ward 12"},
            awaiting_confirmation=False,
            action=validator.ValidatedAction.READY_TO_SUBMIT,
            ask_for=None,
            reply_text=None,
            summary={"issue_type": "पानी नहीं", "location": "Ward 12"},
        ),
    )
    canned_ticket = api.Ticket(
        complaint_id="SMD-0001",
        department="Jal Vibhag",
        office=api.Office(name="Ward 12 Office", level=api.OfficeLevel.WARD),
        status=api.ComplaintStatus.NEW,
    )
    monkeypatch.setattr(routes.ticketing, "create_ticket", lambda **kwargs: canned_ticket)
    saved = {}
    monkeypatch.setattr(routes.session, "save_turn", lambda **kwargs: saved.update(kwargs))

    response = post(test_client, text="haan")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "submitted"
    assert "SMD-0001" in body["reply_text"]
    assert body["ticket"]["complaint_id"] == "SMD-0001"
    update = saved["session_update"]
    assert update.status == session.SessionStatus.COMPLETED
    assert update.collected_fields == {}


def test_turn_engine_unavailable_is_503(test_client, monkeypatch):
    def raise_unavailable(**kwargs):
        raise turn_engine.TurnEngineUnavailable("both providers down")

    monkeypatch.setattr(routes.turn_engine, "run_turn", raise_unavailable)

    response = post(test_client, text="paani nahi aa raha")

    assert response.status_code == 503
    assert response.json()["error_code"] == "SERVICE_UNAVAILABLE"


# --- GET /status/{complaint_id} (T19, S11) ------------------------------------------------------


def test_status_returns_200_for_a_real_ticket(test_client, monkeypatch):
    monkeypatch.setattr(
        routes.ticketing,
        "get_status",
        lambda complaint_id: {
            "status": "in_progress",
            "department": "Jal Vibhag",
            "updated_at": "2026-09-29T09:15:00Z",
        },
    )

    response = test_client.get("/api/v1/status/SMD-0042")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "complaint_id": "SMD-0042",
        "status": "in_progress",
        "department": "Jal Vibhag",
        "updated_at": "2026-09-29T09:15:00Z",
    }


def test_status_malformed_id_is_400(test_client, monkeypatch):
    monkeypatch.setattr(routes.ticketing, "get_status", raise_if_called)

    response = test_client.get("/api/v1/status/SMD-ABC")

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_COMPLAINT_ID"


def test_status_unknown_id_is_404(test_client, monkeypatch):
    monkeypatch.setattr(routes.ticketing, "get_status", lambda complaint_id: None)

    response = test_client.get("/api/v1/status/SMD-9999")

    assert response.status_code == 404
    assert response.json()["error_code"] == "COMPLAINT_NOT_FOUND"


# --- Speak (T51, S17) ------------------------------------------------------------------------


def test_speak_returns_audio(test_client, monkeypatch):
    monkeypatch.setattr(routes.tts, "synthesize", lambda text: "base64audio")

    response = test_client.post("/api/v1/speak", json={"text": "नमस्ते"})

    assert response.status_code == 200
    assert response.json() == {"audio_base64": "base64audio"}


def test_speak_empty_text_is_400(test_client, monkeypatch):
    monkeypatch.setattr(routes.tts, "synthesize", raise_if_called)

    response = test_client.post("/api/v1/speak", json={"text": ""})

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_INPUT"


def test_speak_too_long_is_400(test_client, monkeypatch):
    monkeypatch.setattr(routes.tts, "synthesize", raise_if_called)

    response = test_client.post("/api/v1/speak", json={"text": "अ" * 1001})

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_INPUT"


def test_speak_provider_down_is_503(test_client, monkeypatch):
    def raise_unavailable(text):
        raise routes.tts.TtsUnavailable("both failed")

    monkeypatch.setattr(routes.tts, "synthesize", raise_unavailable)

    response = test_client.post("/api/v1/speak", json={"text": "नमस्ते"})

    assert response.status_code == 503
    assert response.json()["error_code"] == "SERVICE_UNAVAILABLE"
