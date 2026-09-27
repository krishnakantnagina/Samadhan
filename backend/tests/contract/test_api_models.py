"""Unit tests for schemas.py itself: models, limits and shared helpers."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    ERROR_REPLY_TEXT,
    ERROR_STATUS,
    Action,
    Command,
    ErrorCode,
    MessageRequest,
    check_message_inputs,
    normalise_content_type,
    parse_command,
)

SESSION = "b7d0c2f4-5a91-4c1e-8d3a-0e6f1a2b9c77"
MESSAGE = "3b1f6c1e-8a4e-4d0a-9f55-2f6d1c7a9e10"


def test_action_values_match_the_spec():
    assert {a.value for a in Action} == {
        "ask",
        "confirm",
        "submitted",
        "cancelled",
        "out_of_scope",
        "error",
    }


def test_every_error_code_has_a_status_and_a_citizen_reply():
    assert set(ERROR_STATUS) == set(ErrorCode)
    assert set(ERROR_REPLY_TEXT) == set(ErrorCode)
    assert all(text.strip() for text in ERROR_REPLY_TEXT.values())


def test_request_text_is_trimmed():
    request = MessageRequest(session_id=SESSION, message_id=MESSAGE, text="  hello  ")
    assert request.text == "hello"


def test_request_requires_lat_and_lng_together():
    with pytest.raises(ValidationError):
        MessageRequest(session_id=SESSION, message_id=MESSAGE, lat=23.2)
    MessageRequest(session_id=SESSION, message_id=MESSAGE, lat=23.2, lng=77.4)


@pytest.mark.parametrize(
    "kwargs, valid",
    [
        ({"text": "hi", "has_audio": False, "lat": None, "lng": None}, True),
        ({"text": None, "has_audio": True, "lat": None, "lng": None}, True),
        ({"text": None, "has_audio": False, "lat": 1.0, "lng": 2.0}, True),
        ({"text": "hi", "has_audio": False, "lat": 1.0, "lng": 2.0}, True),
        ({"text": None, "has_audio": False, "lat": None, "lng": None}, False),
        ({"text": "hi", "has_audio": True, "lat": None, "lng": None}, False),
        ({"text": "  ", "has_audio": False, "lat": None, "lng": None}, False),
        ({"text": "hi", "has_audio": False, "lat": 1.0, "lng": None}, False),
    ],
)
def test_check_message_inputs(kwargs, valid):
    assert (check_message_inputs(**kwargs) is None) is valid


def test_normalise_content_type():
    assert normalise_content_type("audio/webm;codecs=opus") == "audio/webm"
    assert normalise_content_type(" Audio/OGG ") == "audio/ogg"
    assert normalise_content_type(None) == ""


def test_parse_command():
    assert parse_command(" Cancel ") is Command.CANCEL
    assert parse_command("RESTART") is Command.RESTART
    assert parse_command("cancel my complaint") is None
    assert parse_command(None) is None
