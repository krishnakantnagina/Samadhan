# Plan: T18 — Real `/message`

Ticket: `docs/TICKETS.md` T18 (owner Dev, depends on T14–T17 — all `[x]`, done when "Text → ticket").
Spec: `docs/specs/S04-message-endpoint.md` §2 (rewritten this session against the real S05–S10
signatures — no new spec number needed, S04 already owns T18).

**Scope: T18 only.** This plan adds the `POST /message` route body to `backend/app/routes.py`. It
does not touch `backend/app/main.py` (already wires `routes.router` in at T07 — zero changes
needed), does not touch `backend/mock/*`, and does not add `GET /status/{complaint_id}` (T19).

**Decisions this plan assumes (already resolved in the rewritten S04 §2, DECISIONS D-S04-3…7):**
- The route is a plain sync `def`, not `async def` (D-S04-3) — every downstream call is already
  synchronous, and FastAPI thread-pools a sync route automatically.
- Any audio submission that passes type/size checks still gets `503 SERVICE_UNAVAILABLE` — S12
  doesn't exist yet (D-S04-4).
- `restart` clears `lat`/`lng` in addition to `collected_fields` (D-S04-5).
- Cancel/restart reply text is duplicated from `mock/app.py`'s constants, not imported (D-S04-6).
- `original_text` is built by joining `ValidationResult.summary`'s values (D-S04-7) — resolves
  S10's former G-S10-1.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `backend/app/routes.py` | Edit | Add the `POST /message` route body — the T18 deliverable |
| `backend/tests/test_routes.py` | Create | Orchestration-level tests: right calls, right order, right error mapping, via a local test `FastAPI` app + monkeypatched collaborators |
| `backend/tests/contract/conftest.py` | Edit | Let the contract suite run in-process against the real app (`CONTRACT_TARGET=real`, no `BASE_URL`) — currently it only supports the mock in-process, or a real app over an actual running server |
| `docs/TICKETS.md` | Edit (last step) | Tick T18 `[x]` |

Not touched: `backend/app/main.py` (already includes `routes.router` at `/api/v1` since T07 — no
change needed), `backend/mock/*`, `backend/app/session.py`/`turn_engine.py`/`validator.py`/
`ticketing.py`/`jurisdiction.py` (all already built and tested; T18 only calls them).

## 2. Steps, in order

**S1 — `backend/app/routes.py`: imports and reply-text constants.**
```python
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import UUID4

from app import schemas as api
from app import session, ticketing, turn_engine, validator
from mock.errors import ApiError

router = APIRouter()

REPLY_CANCELLED = "आपकी शिकायत रद्द कर दी गई है।"          # D-S04-6: matches mock/app.py verbatim
REPLY_RESTART = "ठीक है, शुरू से शुरू करते हैं। आपकी क्या समस्या है?"  # ditto


def _submitted_reply(complaint_id: str) -> str:
    return f"आपकी शिकायत दर्ज हो गई है। शिकायत क्रमांक: {complaint_id}।"
```
`from app import session, ...` (module imports, not individual functions) so tests can
`monkeypatch.setattr(routes.session, "get_or_create_session", fake)` cleanly.

**S2 — The route: input validation (S04 §2 step 1).**
```python
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
    problem = api.check_message_inputs(text=text, has_audio=audio is not None, lat=lat, lng=lng)
    if problem:
        raise ApiError(api.ErrorCode.INVALID_INPUT, problem)

    if audio is not None:
        if api.normalise_content_type(audio.content_type) not in api.ACCEPTED_AUDIO_TYPES:
            raise ApiError(api.ErrorCode.UNSUPPORTED_AUDIO, f"Unsupported: {audio.content_type}.")
        if (audio.size or 0) > api.AUDIO_MAX_BYTES:
            raise ApiError(api.ErrorCode.AUDIO_TOO_LARGE, f"Audio over {api.AUDIO_MAX_BYTES} bytes.")
        raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, "Voice input is not available yet.")
```
`audio.size`/`audio.content_type` are plain attributes (no `await` needed — confirmed against the
installed FastAPI's own `UploadFile` docs, which recommend exactly this for sync routes).

**S3 — Dedupe and session load (steps 2–3).**
```python
    stored = session.find_stored_response(session_id, message_id)
    if stored is not None:
        return stored.model_copy(update={"duplicate": True})

    row = session.get_or_create_session(session_id)
```

**S4 — Command check (step 4).**
```python
    command = api.parse_command(text)
    if command is api.Command.CANCEL:
        response = api.MessageResponse(
            session_id=session_id, message_id=message_id, action=api.Action.CANCELLED,
            ask_for=None, reply_text=REPLY_CANCELLED, transcript=None, summary=None,
            ticket=None, duplicate=False,
        )
        update = session.SessionUpdate(
            collected_fields={}, awaiting_confirmation=False, lat=None, lng=None,
            status=session.SessionStatus.CANCELLED,
        )
        return _persist(session_id, message_id, text, response, update)

    if command is api.Command.RESTART:
        response = api.MessageResponse(
            session_id=session_id, message_id=message_id, action=api.Action.ASK,
            ask_for=None, reply_text=REPLY_RESTART, transcript=None, summary=None,
            ticket=None, duplicate=False,
        )
        update = session.SessionUpdate(
            collected_fields={}, awaiting_confirmation=False, lat=None, lng=None,
            status=session.SessionStatus.ACTIVE,
        )
        return _persist(session_id, message_id, text, response, update)
```

**S5 — Turn Engine + Validator (steps 6–7).**
```python
    state = turn_engine.SessionState(row.service_id, row.collected_fields, row.awaiting_confirmation)
    recent = session.get_recent_messages(session_id)
    try:
        turn_result = turn_engine.run_turn(
            session=state, specs=request.app.state.specs, text=text, lat=lat, lng=lng,
            recent_messages=recent,
        )
    except turn_engine.TurnEngineUnavailable as exc:
        raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc

    snapshot = validator.SessionSnapshot(
        row.service_id, row.collected_fields, row.awaiting_confirmation, row.lat, row.lng
    )
    result = validator.apply(
        specs=request.app.state.specs, session=snapshot, turn_result=turn_result, lat=lat, lng=lng
    )
```

**S6 — Ticket creation or a normal reply (step 8).**
```python
    if result.action == validator.ValidatedAction.READY_TO_SUBMIT:
        spec = request.app.state.specs[result.service_id]
        original_text = "; ".join(str(v) for v in (result.summary or {}).values())
        ticket = ticketing.create_ticket(
            session_id=session_id, spec=spec, validated_fields=result.collected_fields,
            lat=lat, lng=lng, original_text=original_text, audio_path=None,
        )
        response = api.MessageResponse(
            session_id=session_id, message_id=message_id, action=api.Action.SUBMITTED,
            ask_for=None, reply_text=_submitted_reply(ticket.complaint_id), transcript=None,
            summary=None, ticket=ticket, duplicate=False,
        )
        update = session.SessionUpdate(
            collected_fields={}, awaiting_confirmation=False, lat=None, lng=None,
            status=session.SessionStatus.COMPLETED,
        )
    else:
        response = api.MessageResponse(
            session_id=session_id, message_id=message_id,
            action=api.Action(result.action.value), ask_for=result.ask_for,
            reply_text=result.reply_text, transcript=None, summary=result.summary,
            ticket=None, duplicate=False,
        )
        update = session.SessionUpdate(
            collected_fields=result.collected_fields,
            awaiting_confirmation=result.awaiting_confirmation,
            lat=lat if lat is not None else row.lat,
            lng=lng if lng is not None else row.lng,
            status=session.SessionStatus.ACTIVE,
        )

    return _persist(session_id, message_id, text, response, update)
```

**S7 — Persist helper (step 9).**
```python
def _persist(session_id, message_id, text, response, update) -> api.MessageResponse:
    input_type = session.InputType.TEXT if text is not None else session.InputType.LOCATION
    session.save_turn(
        session_id=session_id, message_id=message_id, input_type=input_type, text=text,
        transcript=None, audio_path=None, response=response, session_update=update,
    )
    return response
```

**S8 — `backend/tests/test_routes.py`: a local test app.**
```python
@pytest.fixture
def test_client(monkeypatch):
    app = FastAPI()
    register_error_handlers(app)
    app.state.specs = {SPEC.service: SPEC}
    app.include_router(routes.router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)
```
Reuses `mock/errors.py`'s `register_error_handlers` (same as `main.py`) and a minimal hand-built
`ServiceSpec` (same shape used in `test_validator.py`/`test_ticketing.py`). Individual tests
monkeypatch `routes.session`/`routes.turn_engine`/`routes.validator`/`routes.ticketing`'s functions
directly — these modules are already fully tested on their own; these tests check only that
`routes.py` calls them correctly, in the right order, and maps results/errors correctly.

**S9 — Tests.**
- `test_audio_rejected_as_service_unavailable` — a small valid audio file → `503`, and
  `session.get_or_create_session` is never called (monkeypatched to raise if it is) — confirms
  audio short-circuits before touching the session at all.
- `test_unsupported_audio_type_is_415` / `test_oversized_audio_is_413` — confirm these checks still
  run and take priority over the blanket `503` (D-S04-4's ordering).
- `test_duplicate_message_id_short_circuits` — `session.find_stored_response` monkeypatched to
  return a canned response; assert `duplicate=True` in the reply and that
  `get_or_create_session`/`run_turn`/`save_turn` are never called.
- `test_cancel_never_reaches_turn_engine` — `text="cancel"`; `run_turn` monkeypatched to raise if
  called; assert `action=cancelled` and the `SessionUpdate` passed to a monkeypatched `save_turn`
  has `status=CANCELLED` and cleared fields.
- `test_restart_clears_lat_lng_too` — `text="restart"`; assert the `SessionUpdate` passed to
  `save_turn` has `lat=None, lng=None` (D-S04-5), not just `collected_fields={}`.
- `test_ask_flow_returns_200_with_ask_for` — `run_turn`/`apply` monkeypatched to return canned
  `TurnResult`/`ValidationResult` with `action=ask`; assert the HTTP response's `action`/`ask_for`/
  `reply_text` match.
- `test_ready_to_submit_creates_ticket_and_clears_session` — `apply` monkeypatched to return
  `READY_TO_SUBMIT`; `ticketing.create_ticket` monkeypatched to return a canned `Ticket`; assert
  `action=submitted`, `reply_text` contains the ticket's `complaint_id`, and the `SessionUpdate`
  passed to `save_turn` has `status=COMPLETED` and cleared fields.
- `test_turn_engine_unavailable_is_503` — `run_turn` monkeypatched to raise
  `TurnEngineUnavailable` → HTTP `503`.
- `test_messages_saved_before_session_state` (indirect) — not re-tested here; already covered by
  `test_session.py`'s own `test_save_turn_writes_message_then_updates_session_in_order` — `routes.py`
  just calls `save_turn` once per turn, it doesn't re-implement that ordering.

**S10 — `backend/tests/contract/conftest.py`.**
```python
@pytest.fixture(scope="session")
def client():
    if BASE_URL:
        with httpx.Client(base_url=BASE_URL, timeout=30) as http:
            yield http
        return

    from fastapi.testclient import TestClient

    if TARGET == "real":
        from app.main import app
    else:
        from mock.app import app

    with TestClient(app, raise_server_exceptions=False) as http:
        yield http
```
Lets `CONTRACT_TARGET=real uv run pytest` (no `BASE_URL`) exercise `app.main:app` in-process — needs
real `.env` credentials (Groq/Gemini/Supabase) since nothing is mocked at this level; not run by
default (`uv run pytest` with no env vars still hits the mock, unchanged).

**S11 — Run the suite and lint.** `cd backend; uv run pytest` (mock-mode contract suite +
`test_routes.py` + everything else, all with no real credentials needed) and
`uv run ruff check . && uv run ruff format --check .`.

**S12 — Tick it off.** `docs/TICKETS.md`: T18 `[x]`, once S11 is green.

## 3. Acceptance coverage

| S04 T18 acceptance item | Covered by |
|---|---|
| `cancel`/`restart` never reach the Turn Engine | S9 `test_cancel_never_reaches_turn_engine`, `test_restart_clears_lat_lng_too` |
| Both LLM providers down → `503`, not `500` | S9 `test_turn_engine_unavailable_is_503` |
| Duplicate `message_id` → stored response, no reprocessing | S9 `test_duplicate_message_id_short_circuits` |
| Any audio → `503` (temporary, D-S04-4) | S9 `test_audio_rejected_as_service_unavailable` + the 415/413 ordering tests |
| Scenario 3/7/8/9/10 (real, multi-module) | **Manual/optional** — the contract suite against `CONTRACT_TARGET=real` (S10 step), which needs real credentials; not part of the default `uv run pytest` |

## 4. New libraries
None.

## 5. How existing tests stay unaffected
`backend/mock/*` and its own contract-suite path (`BASE_URL` unset, `CONTRACT_TARGET` unset/`mock`)
are untouched — S10's `conftest.py` change only adds a new branch, it doesn't change the default.
`test_session.py`/`test_turn_engine.py`/`test_validator.py`/`test_jurisdiction.py`/
`test_ticketing.py` are untouched; `test_routes.py` monkeypatches their public functions, never
their internals.

## Verification
1. `cd backend; uv run pytest` — new tests green, all existing ones (including the mock-mode
   contract suite) unaffected.
2. `cd backend; uv run ruff check . && uv run ruff format --check .` — clean.
3. Manual, needs real `.env` + a running/importable real app: `cd backend;
   CONTRACT_TARGET=real uv run pytest tests/contract` (in-process, via S10's `conftest.py` change) —
   confirms the actual end-to-end text flow against live Groq/Gemini/Supabase, skipping
   `mock_only`-marked tests. This is the closest thing to PROJECT.md's "text complaint → ticket on
   dashboard" milestone actually running for real.

## Not doing in this turn
Not implementing `routes.py`'s route body itself until this plan is reviewed — same two-step
pattern as T12/T14/T15/T16/T17.
