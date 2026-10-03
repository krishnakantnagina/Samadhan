"""T18 -- POST /api/v1/message. T19 -- GET /status/{complaint_id}. T26 -- voice (S12).
Spec: docs/specs/S04-message-endpoint.md section 2, docs/specs/S11-status-lookup.md,
docs/specs/S12-voice.md.

Plain sync `def` routes, not `async def` -- every downstream call (S05/S06/S09/S10/S12) is already
synchronous, and FastAPI thread-pools a sync route automatically (S04 D-S04-3). Audio bytes are read
via `audio.file.read()` (sync, blocking) rather than `await audio.read()`, exactly as FastAPI's own
`UploadFile` docs recommend for `def` routes -- keeps the whole route sync, D-S04-3's reasoning.
"""

import re
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from pydantic import UUID4

from app import schemas as api
from app import auth, intake, session, status_reply, ticketing, tts, turn_engine, validator, voice
from mock.errors import ApiError

router = APIRouter()

REPLY_EMPTY_TRANSCRIPT = "मुझे आपकी बात समझ नहीं आई। कृपया दोबारा बोलें या लिखकर बताएं।"  # S01 D-A6
REPLY_LOGIN_HI = "शिकायत दर्ज करने के लिए कृपया अपना मोबाइल नंबर बताकर लॉगिन करें। इसी नंबर पर संबंधित अधिकारी आपसे संपर्क करेंगे।"  # S31


def _submitted_reply(complaint_id: str) -> str:
    return f"आपकी शिकायत दर्ज हो गई है। शिकायत क्रमांक: {complaint_id}।"


def _persist(
    *,
    session_id,
    message_id,
    input_type,
    text,
    transcript,
    audio_path,
    response,
    update,
) -> api.MessageResponse:
    session.save_turn(
        session_id=session_id,
        message_id=message_id,
        input_type=input_type,
        text=text,
        transcript=transcript,
        audio_path=audio_path,
        response=response,
        session_update=update,
    )
    return response


def _command_response(
    command: api.Command, session_id, message_id, transcript: str | None
) -> api.MessageResponse:
    cancelled = command is api.Command.CANCEL
    return api.MessageResponse(
        session_id=session_id,
        message_id=message_id,
        action=api.Action.CANCELLED if cancelled else api.Action.ASK,
        ask_for=None,
        reply_text=api.REPLY_CANCELLED if cancelled else api.REPLY_RESTART,
        transcript=transcript,
        summary=None,
        ticket=None,
        duplicate=False,
    )


def _status_turn(
    *, complaint_id: str, session_id, message_id, transcript, row, text, audio, audio_path
) -> api.MessageResponse:
    """S29: answer a status question with the public status fields only, leaving the session untouched."""
    reply = status_reply.build_status_reply(complaint_id, ticketing.get_status(complaint_id))
    response = api.MessageResponse(
        session_id=session_id,
        message_id=message_id,
        action=api.Action.OUT_OF_SCOPE,
        ask_for=None,
        reply_text=reply,
        transcript=transcript,
        summary=None,
        ticket=None,
        duplicate=False,
    )
    update = session.SessionUpdate(
        collected_fields=row.collected_fields,
        awaiting_confirmation=row.awaiting_confirmation,
        lat=row.lat,
        lng=row.lng,
        status=session.SessionStatus.ACTIVE,
        service_id=row.service_id,
    )
    return _persist(
        session_id=session_id,
        message_id=message_id,
        input_type=session.InputType.AUDIO if audio is not None else session.InputType.TEXT,
        text=text,
        transcript=transcript,
        audio_path=audio_path,
        response=response,
        update=update,
    )


def _command_update(command: api.Command) -> session.SessionUpdate:
    # S06 RULES 3: the caller clears fields when setting a terminal status. lat/lng are cleared
    # for restart too, not just collected_fields (D-S04-5).
    return session.SessionUpdate(
        collected_fields={},
        awaiting_confirmation=False,
        lat=None,
        lng=None,
        status=(
            session.SessionStatus.CANCELLED
            if command is api.Command.CANCEL
            else session.SessionStatus.ACTIVE
        ),
        service_id=None,  # a cancelled/restarted complaint starts over (S23 5b)
    )


def _intake_ask(*, pre, row, session_id, message_id, text, audio, audio_path, transcript) -> api.MessageResponse:
    """S30: intake v2 asks its one department question instead of running the validator. The session keeps its intake notes."""
    response = api.MessageResponse(
        session_id=session_id, message_id=message_id, action=api.Action.ASK, ask_for=pre.ask_for, reply_text=pre.ask,
        transcript=transcript, summary=None, ticket=None, duplicate=False,
    )
    update = session.SessionUpdate(
        collected_fields={**row.collected_fields, intake.META_KEY: pre.meta}, awaiting_confirmation=False, lat=row.lat, lng=row.lng,
        status=session.SessionStatus.ACTIVE, service_id=row.service_id,
    )
    input_type = session.InputType.AUDIO if audio is not None else session.InputType.TEXT if text is not None else session.InputType.LOCATION
    return _persist(
        session_id=session_id, message_id=message_id, input_type=input_type, text=text, transcript=transcript,
        audio_path=audio_path, response=response, update=update,
    )


@router.post("/message", response_model=api.MessageResponse)
def message(
    request: Request,
    session_id: Annotated[UUID4, Form()],
    message_id: Annotated[UUID4, Form()],
    text: Annotated[str | None, Form()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
    lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Form(ge=-180, le=180)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> api.MessageResponse:
    # Step 1: validate input (S04 section 2 step 1)
    problem = api.check_message_inputs(text=text, has_audio=audio is not None, lat=lat, lng=lng)
    if problem:
        raise ApiError(api.ErrorCode.INVALID_INPUT, problem)

    content_type = api.normalise_content_type(audio.content_type) if audio is not None else None
    if audio is not None:
        if content_type not in api.ACCEPTED_AUDIO_TYPES:
            raise ApiError(api.ErrorCode.UNSUPPORTED_AUDIO, f"Unsupported: {audio.content_type}.")
        if (audio.size or 0) > api.AUDIO_MAX_BYTES:
            raise ApiError(
                api.ErrorCode.AUDIO_TOO_LARGE, f"Audio over {api.AUDIO_MAX_BYTES} bytes."
            )

    # Step 2: dedupe on message_id (S06)
    stored = session.find_stored_response(session_id, message_id)
    if stored is not None:
        return stored.model_copy(update={"duplicate": True})

    # Step 3: load or create session (S06)
    row = session.get_or_create_session(session_id)

    # Step 5: audio -> transcript (S12)
    transcript: str | None = None
    audio_path: str | None = None
    if audio is not None:
        try:
            result = voice.transcribe(audio.file.read(), content_type, session_id, message_id)
        except voice.VoiceUnavailable as exc:
            raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc
        transcript, audio_path = result.transcript, result.audio_path

        if not transcript.strip():
            # Empty/unintelligible transcript is not an error (S01 D-A6) -- action=error, HTTP 200
            response = api.MessageResponse(
                session_id=session_id,
                message_id=message_id,
                action=api.Action.ERROR,
                ask_for=None,
                reply_text=REPLY_EMPTY_TRANSCRIPT,
                transcript=transcript,
                summary=None,
                ticket=None,
                duplicate=False,
            )
            update = session.SessionUpdate(
                collected_fields=row.collected_fields,
                awaiting_confirmation=row.awaiting_confirmation,
                lat=row.lat,
                lng=row.lng,
                status=session.SessionStatus.ACTIVE,
                service_id=row.service_id,
            )
            return _persist(
                session_id=session_id,
                message_id=message_id,
                input_type=session.InputType.AUDIO,
                text=None,
                transcript=transcript,
                audio_path=audio_path,
                response=response,
                update=update,
            )

    effective_text = text if text is not None else transcript

    # Step 5b: command check (S01 D-A3, amended by S20 section 5) -- on the typed text or the
    # transcript, so a spoken cancel/restart works. Never reaches the Turn Engine.
    command = api.parse_command(effective_text)
    if command is not None:
        input_type = session.InputType.AUDIO if audio is not None else session.InputType.TEXT
        return _persist(
            session_id=session_id,
            message_id=message_id,
            input_type=input_type,
            text=text,
            transcript=transcript,
            audio_path=audio_path,
            response=_command_response(command, session_id, message_id, transcript),
            update=_command_update(command),
        )

    # Step 5c: a complaint number in a short message is a status question (S29): answered here, no LLM.
    status_id = status_reply.extract_complaint_id(effective_text)
    if status_id is not None:
        return _status_turn(
            complaint_id=status_id, session_id=session_id, message_id=message_id,
            transcript=transcript, row=row, text=text, audio=audio, audio_path=audio_path,
        )  # fmt: skip

    # Step 6: Turn Engine (S05)
    state = turn_engine.SessionState(
        row.service_id, row.collected_fields, row.awaiting_confirmation
    )
    recent = session.get_recent_messages(session_id)
    try:
        turn_result = turn_engine.run_turn(
            session=state,
            specs=request.app.state.specs,
            text=effective_text,
            lat=lat,
            lng=lng,
            recent_messages=recent,
        )
    except turn_engine.TurnEngineUnavailable as exc:
        raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc

    # Step 6b: the LLM says this is a status question (S29): use a bare number if there is one.
    if turn_result.intent == "status":
        status_id = status_reply.extract_complaint_id(effective_text, allow_bare=True)
        if status_id is not None:
            return _status_turn(
                complaint_id=status_id, session_id=session_id, message_id=message_id,
                transcript=transcript, row=row, text=text, audio=audio, audio_path=audio_path,
            )  # fmt: skip

    # Step 6c: intake v2 (S30, flag INTAKE_V2, off by default): Jev decides the department; it may ask ONE question here
    # or send the complaint to the Human Evaluation queue. Disabled / no key / Jev down: returns the turn unchanged.
    pre = intake.prestep(row=row, specs=request.app.state.specs, text=effective_text, recent=recent, turn_result=turn_result)
    turn_result = pre.turn_result
    if pre.ask is not None:
        return _intake_ask(
            pre=pre, row=row, session_id=session_id, message_id=message_id, text=text, audio=audio,
            audio_path=audio_path, transcript=transcript,
        )

    # Step 7: Validator (S07)
    snapshot = validator.SessionSnapshot(
        row.service_id, row.collected_fields, row.awaiting_confirmation, row.lat, row.lng
    )
    result = validator.apply(
        specs=request.app.state.specs, session=snapshot, turn_result=turn_result, lat=lat, lng=lng
    )
    result = intake.poststep(result=result, pre=pre, specs=request.app.state.specs, lat=lat, lng=lng, row=row, text=effective_text, recent=recent)  # S30/S33: notes, triage questions, location detail, duration

    # Step 7b: S31 registration. Filing a complaint needs a logged-in citizen (AUTH_REQUIRED=1): the confirmed draft is KEPT and the client is asked to
    # log in, then to confirm again. Enquiries, status checks and every earlier question never need login.
    user = auth.user_from_header(authorization)
    if result.action == validator.ValidatedAction.READY_TO_SUBMIT and auth.required() and user is None:
        result = result.model_copy(update={"action": validator.ValidatedAction.ASK, "ask_for": "login", "reply_text": REPLY_LOGIN_HI, "awaiting_confirmation": True})

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
            audio_path=audio_path,
            user_id=user.id if user else None,
        )
        response = api.MessageResponse(
            session_id=session_id,
            message_id=message_id,
            action=api.Action.SUBMITTED,
            ask_for=None,
            reply_text=_submitted_reply(ticket.complaint_id),
            transcript=transcript,
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
            service_id=None,
        )
    else:
        response = api.MessageResponse(
            session_id=session_id,
            message_id=message_id,
            action=api.Action(result.action.value),
            ask_for=result.ask_for,
            reply_text=result.reply_text,
            transcript=transcript,
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
            service_id=result.service_id,
        )

    # Step 9: persist and respond
    input_type = (
        session.InputType.AUDIO
        if audio is not None
        else session.InputType.TEXT
        if text is not None
        else session.InputType.LOCATION
    )
    return _persist(
        session_id=session_id,
        message_id=message_id,
        input_type=input_type,
        text=text,
        transcript=transcript,
        audio_path=audio_path,
        response=response,
        update=update,
    )


@router.post("/speak", response_model=api.SpeakResponse)
def speak(body: api.SpeakRequest) -> api.SpeakResponse:
    """S17 -- text-to-speech reply (T51). Stateless: no session, no DB write (S17 RULES 1)."""
    try:
        audio_base64 = tts.synthesize(body.text)
    except tts.TtsUnavailable as exc:
        raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc
    return api.SpeakResponse(audio_base64=audio_base64)


@router.get("/status/{complaint_id}", response_model=api.StatusResponse)
def status(complaint_id: str) -> api.StatusResponse:
    if not re.fullmatch(api.COMPLAINT_ID_PATTERN, complaint_id):
        raise ApiError(api.ErrorCode.INVALID_COMPLAINT_ID, f"Bad complaint_id: {complaint_id!r}.")
    row = ticketing.get_status(complaint_id)
    if row is None:
        raise ApiError(api.ErrorCode.COMPLAINT_NOT_FOUND, f"No ticket {complaint_id}.")
    return api.StatusResponse(
        complaint_id=complaint_id,
        status=row["status"],
        department=row["department"],
        updated_at=row["updated_at"],
    )
