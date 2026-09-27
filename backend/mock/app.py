"""Mock of the S01 API contract (T08).

Returns schema-valid canned responses for every `action` so the website can be built
against it. Deterministic rules, checked in this order:

1. text `mock:<trigger>` forces a response: ask, confirm, submitted, submitted_district,
   cancelled, out_of_scope, error. (Mock-only; the real API has no triggers.)
2. text `cancel` / `restart` are the S01 commands.
3. audio            -> action=ask for location, with a transcript.
4. lat + lng        -> action=submitted, routed to a ward office.
5. anything else    -> action=ask for location.

State is in memory and single-process. Audio duration is not checked (needs decoding);
only content type and size are.
"""

import itertools
import os
import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from app import schemas as api
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import UUID4

from .errors import ApiError, register_error_handlers

MOCK_PREFIX = "mock:"
DEPARTMENT = "Jal Vibhag"

REPLY_ASK_LOCATION = "आपकी समस्या दर्ज कर ली है। कृपया अपना वार्ड या इलाका बताइए, या लोकेशन साझा कीजिए।"
REPLY_RESTART = "ठीक है, शुरू से शुरू करते हैं। आपकी क्या समस्या है?"
REPLY_CONFIRM = "कृपया जाँच लें: पानी की आपूर्ति 3 दिन से बंद है, वार्ड 12। क्या यह सही है?"
REPLY_CANCELLED = "आपकी शिकायत रद्द कर दी गई है।"
REPLY_OUT_OF_SCOPE = "क्षमा करें, मैं अभी केवल पानी की आपूर्ति से जुड़ी शिकायतों में मदद कर सकता हूँ।"
REPLY_ERROR = "मुझे आपकी बात समझ नहीं आई। कृपया दोबारा बोलें या लिखकर बताएं।"
MOCK_TRANSCRIPT = "3 दिन से पानी नहीं आ रहा"

_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

_responses: dict[tuple[UUID, UUID], api.MessageResponse] = {}
_ticket_numbers = itertools.count(100)
_tickets: dict[str, dict] = {
    "SMD-0042": {
        "status": api.ComplaintStatus.IN_PROGRESS,
        "department": DEPARTMENT,
        "updated_at": datetime(2026, 9, 29, 9, 15, tzinfo=UTC),
    },
    "SMD-0007": {
        "status": api.ComplaintStatus.NEEDS_REVIEW,
        "department": DEPARTMENT,
        "updated_at": datetime(2026, 9, 28, 18, 0, tzinfo=UTC),
    },
}

app = FastAPI(title="Samadhan API (mock)", version=api.CONTRACT_VERSION)
register_error_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _new_ticket(
    office_name: str, level: api.OfficeLevel, status: api.ComplaintStatus
) -> api.Ticket:
    complaint_id = f"SMD-{next(_ticket_numbers):04d}"
    _tickets[complaint_id] = {
        "status": status,
        "department": DEPARTMENT,
        "updated_at": datetime.now(UTC),
    }
    return api.Ticket(
        complaint_id=complaint_id,
        department=DEPARTMENT,
        office=api.Office(name=office_name, level=level),
        status=status,
    )


def _submitted(district: bool = False) -> tuple[api.Action, str, dict]:
    if district:
        ticket = _new_ticket(
            "Bhopal District Office", api.OfficeLevel.DISTRICT, api.ComplaintStatus.NEEDS_REVIEW
        )
    else:
        ticket = _new_ticket("Ward 12 Office", api.OfficeLevel.WARD, api.ComplaintStatus.NEW)
    reply = f"आपकी शिकायत दर्ज हो गई है। शिकायत क्रमांक: {ticket.complaint_id}।"
    return api.Action.SUBMITTED, reply, {"ticket": ticket}


def _ask_location() -> tuple[api.Action, str, dict]:
    return api.Action.ASK, REPLY_ASK_LOCATION, {"ask_for": "location"}


def _from_trigger(trigger: str) -> tuple[api.Action, str, dict]:
    canned = {
        "ask": _ask_location,
        "confirm": lambda: (
            api.Action.CONFIRM,
            REPLY_CONFIRM,
            {"summary": {"issue": "no water supply", "duration": "3 days", "ward": "Ward 12"}},
        ),
        "submitted": _submitted,
        "submitted_district": lambda: _submitted(district=True),
        "cancelled": lambda: (api.Action.CANCELLED, REPLY_CANCELLED, {}),
        "out_of_scope": lambda: (api.Action.OUT_OF_SCOPE, REPLY_OUT_OF_SCOPE, {}),
        "error": lambda: (api.Action.ERROR, REPLY_ERROR, {}),
    }
    if trigger not in canned:
        raise ApiError(api.ErrorCode.INVALID_INPUT, f"Unknown mock trigger: {trigger!r}.")
    return canned[trigger]()


def _decide(text: str | None, has_audio: bool, has_location: bool) -> tuple[api.Action, str, dict]:
    cleaned = text.strip() if text is not None else None
    if cleaned and cleaned.lower().startswith(MOCK_PREFIX):
        return _from_trigger(cleaned[len(MOCK_PREFIX) :].strip().lower())
    command = api.parse_command(cleaned)
    if command is api.Command.CANCEL:
        return api.Action.CANCELLED, REPLY_CANCELLED, {}
    if command is api.Command.RESTART:
        return api.Action.ASK, REPLY_RESTART, {}
    if has_audio:
        return (
            api.Action.ASK,
            REPLY_ASK_LOCATION,
            {"ask_for": "location", "transcript": MOCK_TRANSCRIPT},
        )
    if has_location:
        return _submitted()
    return _ask_location()


@app.get("/health", response_model=api.HealthResponse)
def health() -> api.HealthResponse:
    return api.HealthResponse()


@app.post("/api/v1/message", response_model=api.MessageResponse)
async def message(
    session_id: Annotated[UUID4, Form()],
    message_id: Annotated[UUID4, Form()],
    text: Annotated[str | None, Form()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
    lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Form(ge=-180, le=180)] = None,
) -> api.MessageResponse:
    problem = api.check_message_inputs(text=text, has_audio=audio is not None, lat=lat, lng=lng)
    if problem:
        raise ApiError(api.ErrorCode.INVALID_INPUT, problem)

    if audio is not None:
        if api.normalise_content_type(audio.content_type) not in api.ACCEPTED_AUDIO_TYPES:
            raise ApiError(api.ErrorCode.UNSUPPORTED_AUDIO, f"Unsupported: {audio.content_type}.")
        if len(await audio.read()) > api.AUDIO_MAX_BYTES:
            raise ApiError(
                api.ErrorCode.AUDIO_TOO_LARGE, f"Audio over {api.AUDIO_MAX_BYTES} bytes."
            )

    key = (session_id, message_id)
    if key in _responses:
        return _responses[key].model_copy(update={"duplicate": True})

    action, reply_text, extra = _decide(text, audio is not None, lat is not None)
    response = api.MessageResponse(
        session_id=session_id,
        message_id=message_id,
        action=action,
        ask_for=extra.get("ask_for"),
        reply_text=reply_text,
        transcript=extra.get("transcript"),
        summary=extra.get("summary"),
        ticket=extra.get("ticket"),
        duplicate=False,
    )
    _responses[key] = response
    return response


@app.get("/api/v1/status/{complaint_id}", response_model=api.StatusResponse)
def status(complaint_id: str) -> api.StatusResponse:
    if not re.fullmatch(api.COMPLAINT_ID_PATTERN, complaint_id):
        raise ApiError(api.ErrorCode.INVALID_COMPLAINT_ID, f"Bad complaint_id: {complaint_id!r}.")
    ticket = _tickets.get(complaint_id)
    if ticket is None:
        raise ApiError(api.ErrorCode.COMPLAINT_NOT_FOUND, f"No ticket {complaint_id}.")
    return api.StatusResponse(complaint_id=complaint_id, **ticket)
