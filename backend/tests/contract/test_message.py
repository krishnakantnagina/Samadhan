"""POST /api/v1/message — S01 sections 4, 7, 8 and the 10 MVP scenarios (section 10)."""

import re

import pytest
from contract_helpers import assert_error, new_id, post_message

from app.schemas import (
    ACCEPTED_AUDIO_TYPES,
    AUDIO_MAX_BYTES,
    COMPLAINT_ID_PATTERN,
    TEXT_MAX_LENGTH,
    Action,
    ComplaintStatus,
    ErrorCode,
    MessageResponse,
    OfficeLevel,
)

AUDIO = b"\x1aE\xdf\xa3fake-audio"


def message(client, **kwargs) -> MessageResponse:
    response = post_message(client, **kwargs)
    assert response.status_code == 200, response.text
    return MessageResponse.model_validate(response.json())


# --- Valid input ------------------------------------------------------------------------


def test_text_message_returns_valid_response(client):
    session_id, message_id = new_id(), new_id()
    body = message(
        client, session_id=session_id, message_id=message_id, text="3 दिन से पानी नहीं आ रहा"
    )
    assert str(body.session_id) == session_id
    assert str(body.message_id) == message_id
    assert body.reply_text.strip()
    assert body.transcript is None
    assert body.duplicate is False


def test_location_only_message_is_accepted(client):
    message(client, lat=23.2599, lng=77.4126)


def test_location_may_accompany_text(client):
    message(client, text="पानी नहीं आ रहा", lat=23.2599, lng=77.4126)


@pytest.mark.mock_only
@pytest.mark.parametrize(
    "audio_type", [*sorted(ACCEPTED_AUDIO_TYPES), "audio/webm;codecs=opus", "Audio/OGG"]
)
def test_accepted_audio_types_return_transcript(client, audio_type):
    body = message(client, audio=AUDIO, audio_type=audio_type)
    assert body.transcript


# --- Commands (scenario 5) ----------------------------------------------------------------


@pytest.mark.parametrize("text", ["cancel", "  Cancel  ", "CANCEL"])
def test_cancel_command(client, text):
    assert message(client, text=text).action == Action.CANCELLED


def test_restart_command_asks_again(client):
    assert message(client, text="restart").action == Action.ASK


# --- Invalid input (S01 section 4.1, 7) -----------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({}, id="nothing"),
        pytest.param({"text": "   "}, id="blank-text"),
        pytest.param({"text": "x" * (TEXT_MAX_LENGTH + 1)}, id="text-too-long"),
        pytest.param({"text": "hello", "lat": 23.2}, id="lat-without-lng"),
        pytest.param({"text": "hello", "lng": 77.4}, id="lng-without-lat"),
        pytest.param({"text": "hello", "lat": 91, "lng": 77.4}, id="lat-out-of-range"),
        pytest.param({"text": "hello", "lat": 23.2, "lng": 181}, id="lng-out-of-range"),
        pytest.param({"text": "hello", "audio": AUDIO}, id="text-and-audio"),
        pytest.param({"text": "hello", "session_id": "not-a-uuid"}, id="bad-session-id"),
        pytest.param({"text": "hello", "message_id": "not-a-uuid"}, id="bad-message-id"),
        pytest.param({"text": "hello", "omit": ("session_id",)}, id="missing-session-id"),
        pytest.param({"text": "hello", "omit": ("message_id",)}, id="missing-message-id"),
    ],
)
def test_invalid_input_is_400(client, kwargs):
    assert_error(post_message(client, **kwargs), 400, ErrorCode.INVALID_INPUT)


def test_uuid_version_must_be_4(client):
    uuid_v1 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    assert_error(post_message(client, text="hi", session_id=uuid_v1), 400, ErrorCode.INVALID_INPUT)


def test_unsupported_audio_type_is_415(client):
    response = post_message(client, audio=AUDIO, audio_type="audio/mpeg")
    assert_error(response, 415, ErrorCode.UNSUPPORTED_AUDIO)


def test_oversized_audio_is_413(client):
    response = post_message(client, audio=b"0" * (AUDIO_MAX_BYTES + 1))
    assert_error(response, 413, ErrorCode.AUDIO_TOO_LARGE)


# --- Idempotency and session isolation (S01 section 8; scenario 10) ------------------------


def test_repeated_message_id_returns_stored_response_with_duplicate_flag(client):
    session_id, message_id = new_id(), new_id()
    first = message(client, session_id=session_id, message_id=message_id, text="पानी नहीं आ रहा")
    second = message(client, session_id=session_id, message_id=message_id, text="पानी नहीं आ रहा")
    assert first.duplicate is False
    assert second.duplicate is True
    assert second.model_dump(exclude={"duplicate"}) == first.model_dump(exclude={"duplicate"})


def test_same_message_id_in_two_sessions_is_not_a_duplicate(client):
    message_id = new_id()
    one = message(client, session_id=new_id(), message_id=message_id, text="hello")
    two = message(client, session_id=new_id(), message_id=message_id, text="hello")
    assert one.session_id != two.session_id
    assert one.duplicate is False
    assert two.duplicate is False


# --- Response shape per action (S01 section 4.2, 4.3) ---------------------------------------

TRIGGERS = {
    "ask": Action.ASK,
    "confirm": Action.CONFIRM,
    "submitted": Action.SUBMITTED,
    "cancelled": Action.CANCELLED,
    "out_of_scope": Action.OUT_OF_SCOPE,
    "error": Action.ERROR,
}


def test_triggers_cover_every_action():
    assert set(TRIGGERS.values()) == set(Action)


@pytest.mark.mock_only
@pytest.mark.parametrize("trigger, action", TRIGGERS.items())
def test_mock_returns_valid_response_for_every_action(client, trigger, action):
    body = message(client, text=f"mock:{trigger}")
    assert body.action == action
    assert (body.summary is not None) == (action == Action.CONFIRM)
    assert (body.ticket is not None) == (action == Action.SUBMITTED)
    assert (body.ask_for is not None) == (action == Action.ASK)
    assert body.transcript is None


@pytest.mark.mock_only
def test_unknown_mock_trigger_is_rejected(client):
    assert_error(post_message(client, text="mock:nope"), 400, ErrorCode.INVALID_INPUT)


# --- MVP scenarios that need the mock's canned behaviour (S01 section 10.2) ------------------


@pytest.mark.mock_only
def test_scenario_1_voice_asks_only_for_location(client):
    body = message(client, audio=AUDIO)
    assert body.transcript
    assert body.action == Action.ASK
    assert body.ask_for == "location"


@pytest.mark.mock_only
def test_scenario_7_gps_routes_to_ward_office(client):
    body = message(client, lat=23.2599, lng=77.4126)
    assert body.action == Action.SUBMITTED
    assert re.fullmatch(COMPLAINT_ID_PATTERN[1:-1], body.ticket.complaint_id)
    assert body.ticket.office.level == OfficeLevel.WARD


@pytest.mark.mock_only
def test_scenario_8_unknown_location_routes_to_district_needs_review(client):
    body = message(client, text="mock:submitted_district")
    assert body.ticket.office.level == OfficeLevel.DISTRICT
    assert body.ticket.status == ComplaintStatus.NEEDS_REVIEW


@pytest.mark.mock_only
def test_scenario_6_unrelated_request_is_out_of_scope(client):
    body = message(client, text="mock:out_of_scope")
    assert body.action == Action.OUT_OF_SCOPE
    assert body.ticket is None
