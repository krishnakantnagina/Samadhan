"""T18 -- POST /api/v1/message. T19 will add GET /status/{complaint_id} here.
Spec: docs/specs/S04-message-endpoint.md section 2.

Plain sync `def` route, not `async def` -- every downstream call (S05/S06/S09/S10) is already
synchronous, and FastAPI thread-pools a sync route automatically (S04 D-S04-3).
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import UUID4

from app import schemas as api
from app import session, ticketing, turn_engine, validator
from mock.errors import ApiError

router = APIRouter()

REPLY_CANCELLED = "आपकी शिकायत रद्द कर दी गई है।"  # D-S04-6: matches mock/app.py verbatim
REPLY_RESTART = "ठीक है, शुरू से शुरू करते हैं। आपकी क्या समस्या है?"  # ditto


def _submitted_reply(complaint_id: str) -> str:
    return f"आपकी शिकायत दर्ज हो गई है। शिकायत क्रमांक: {complaint_id}।"


def _persist(session_id, message_id, text, response, update) -> api.MessageResponse:
    input_type = session.InputType.TEXT if text is not None else session.InputType.LOCATION
    session.save_turn(
        session_id=session_id,
        message_id=message_id,
        input_type=input_type,
        text=text,
        transcript=None,
        audio_path=None,
        response=response,
        session_update=update,
    )
    return response


@router.post("/message", response_model=api.MessageResponse)
def message(
    request: Request,
    session_id: Annotated[UUID4, Form()],
    message_id: Annotated[UUID4, Form()],
    text: Annotated[str | None, Form()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
    lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Form(ge=-180, le=180)] = None,
) -> api.MessageResponse:
    # Step 1: validate input (S04 section 2 step 1)
    problem = api.check_message_inputs(text=text, has_audio=audio is not None, lat=lat, lng=lng)
    if problem:
        raise ApiError(api.ErrorCode.INVALID_INPUT, problem)

    if audio is not None:
        if api.normalise_content_type(audio.content_type) not in api.ACCEPTED_AUDIO_TYPES:
            raise ApiError(api.ErrorCode.UNSUPPORTED_AUDIO, f"Unsupported: {audio.content_type}.")
        if (audio.size or 0) > api.AUDIO_MAX_BYTES:
            raise ApiError(
                api.ErrorCode.AUDIO_TOO_LARGE, f"Audio over {api.AUDIO_MAX_BYTES} bytes."
            )
        # S12 (voice) doesn't exist yet (T26) -- D-S04-4.
        raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, "Voice input is not available yet.")

    # Step 2: dedupe on message_id (S06)
    stored = session.find_stored_response(session_id, message_id)
    if stored is not None:
        return stored.model_copy(update={"duplicate": True})

    # Step 3: load or create session (S06)
    row = session.get_or_create_session(session_id)

    # Step 4: command check (S01 D-A3) -- commands never reach the Turn Engine
    command = api.parse_command(text)
    if command is api.Command.CANCEL:
        response = api.MessageResponse(
            session_id=session_id,
            message_id=message_id,
            action=api.Action.CANCELLED,
            ask_for=None,
            reply_text=REPLY_CANCELLED,
            transcript=None,
            summary=None,
            ticket=None,
            duplicate=False,
        )
        update = session.SessionUpdate(
            collected_fields={},
            awaiting_confirmation=False,
            lat=None,
            lng=None,
            status=session.SessionStatus.CANCELLED,
        )
        return _persist(session_id, message_id, text, response, update)

    if command is api.Command.RESTART:
        response = api.MessageResponse(
            session_id=session_id,
            message_id=message_id,
            action=api.Action.ASK,
            ask_for=None,
            reply_text=REPLY_RESTART,
            transcript=None,
            summary=None,
            ticket=None,
            duplicate=False,
        )
        update = session.SessionUpdate(
            collected_fields={},
            awaiting_confirmation=False,
            lat=None,  # D-S04-5: GPS is cleared too, not just collected_fields
            lng=None,
            status=session.SessionStatus.ACTIVE,
        )
        return _persist(session_id, message_id, text, response, update)

    # Step 6: Turn Engine (S05)
    state = turn_engine.SessionState(
        row.service_id, row.collected_fields, row.awaiting_confirmation
    )
    recent = session.get_recent_messages(session_id)
    try:
        turn_result = turn_engine.run_turn(
            session=state,
            specs=request.app.state.specs,
            text=text,
            lat=lat,
            lng=lng,
            recent_messages=recent,
        )
    except turn_engine.TurnEngineUnavailable as exc:
        raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc

    # Step 7: Validator (S07)
    snapshot = validator.SessionSnapshot(
        row.service_id, row.collected_fields, row.awaiting_confirmation, row.lat, row.lng
    )
    result = validator.apply(
        specs=request.app.state.specs, session=snapshot, turn_result=turn_result, lat=lat, lng=lng
    )

    # Step 8: ticket creation, or a normal ask/confirm/out_of_scope reply
    if result.action == validator.ValidatedAction.READY_TO_SUBMIT:
        spec = request.app.state.specs[result.service_id]
        original_text = "; ".join(str(v) for v in (result.summary or {}).values())  # D-S04-7
        ticket = ticketing.create_ticket(
            session_id=session_id,
            spec=spec,
            validated_fields=result.collected_fields,
            lat=lat,
            lng=lng,
            original_text=original_text,
            audio_path=None,
        )
        response = api.MessageResponse(
            session_id=session_id,
            message_id=message_id,
            action=api.Action.SUBMITTED,
            ask_for=None,
            reply_text=_submitted_reply(ticket.complaint_id),
            transcript=None,
            summary=None,
            ticket=ticket,
            duplicate=False,
        )
        update = session.SessionUpdate(
            collected_fields={},
            awaiting_confirmation=False,
            lat=None,
            lng=None,
            status=session.SessionStatus.COMPLETED,
        )
    else:
        response = api.MessageResponse(
            session_id=session_id,
            message_id=message_id,
            action=api.Action(result.action.value),
            ask_for=result.ask_for,
            reply_text=result.reply_text,
            transcript=None,
            summary=result.summary,
            ticket=None,
            duplicate=False,
        )
        update = session.SessionUpdate(
            collected_fields=result.collected_fields,
            awaiting_confirmation=result.awaiting_confirmation,
            lat=lat if lat is not None else row.lat,
            lng=lng if lng is not None else row.lng,
            status=session.SessionStatus.ACTIVE,
        )

    # Step 9: persist and respond
    return _persist(session_id, message_id, text, response, update)
