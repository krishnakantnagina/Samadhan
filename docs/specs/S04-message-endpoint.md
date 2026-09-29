# S04 — App Setup & Message Orchestration
Implements: T07 (`backend/app/main.py`), T18 (`backend/app/routes.py`) · Used by: T19 (status, same
app) · Depends on: S01 API contract, S02 DB schema, S03 service spec format, S05 Turn Engine, S06
Session Manager, S07 Validator, S09 Jurisdiction, S10 Ticket + routing · Version: v1 · Status: Draft

## PURPOSE
Wires the real backend together: the FastAPI app itself (T07, done) and the step-by-step handling of
`POST /api/v1/message` (T18). This spec owns orchestration only — *what calls what, in what order,
with which fallback*. Section 1 (T07) is implemented and unchanged. Section 2 (T18) is now written
against the **real** signatures S05/S06/S07/S09/S10 shipped with — every `[DECIDE]` this section
carried before those specs existed is now resolved below (§3), closing former G-S04-1. Voice (S12)
still does not exist (T26); T18 explicitly does not depend on it — see §2 step 1 and D-S04-4.

## SCOPE
`backend/app/main.py` (unchanged since T07) and the body of `backend/app/routes.py`'s
`POST /api/v1/message` (T18, new). `GET /health` and `GET /api/v1/status/{complaint_id}` are named
for completeness (T19) but `/status`'s internals belong to whichever ticket builds it, not here. The
mock (`backend/mock/app.py`, T08) is unaffected — it keeps its canned rules and stays available for
the website and for contract tests. `routes.py` reuses `app/schemas.py` and `mock/errors.py`
verbatim (T07 already imports `register_error_handlers`/`ApiError` from `mock/errors.py` — there is
no separate `app/errors.py`; T18 keeps that existing pattern rather than forking it).

## 1. App setup (T07) — done, unchanged

| Piece | Rule |
|---|---|
| Entry point | `backend/app/main.py`, `app = FastAPI(title="Samadhan API", version=api.CONTRACT_VERSION)` |
| Config | Read via `app/config.py`'s `get_*` functions (T07/T12/T14 added these incrementally). `ALLOWED_ORIGINS` required at import time; `GROQ_*`/`GEMINI_*`/`SUPABASE_*` required once T12/T14 landed (they have) |
| CORS | `CORSMiddleware`, `allow_origins` from `ALLOWED_ORIGINS` (comma-separated), `allow_methods=["GET", "POST"]` — identical to the mock (S01 §9 rule 4) |
| Error handlers | `register_error_handlers(app)` from `mock/errors.py`, unchanged (S01 §7) |
| `GET /health` | No auth, no DB/ASR/LLM call, returns `api.HealthResponse()` — identical to the mock (S01 §6) |
| Router | `backend/app/routes.py`'s `router`, mounted at `/api/v1`; `/health` stays unprefixed |
| Startup | `app.state.specs = service_spec.load_specs(SPECS_DIR)` (S03) via FastAPI `lifespan`, so a broken YAML stops the process before it serves traffic |
| DB / storage client | `app.db.get_client()` (S06, `lru_cache`d, sync `supabase-py`) — built lazily on first use by `app.session`/`app.jurisdiction`/`app.ticketing`, not eagerly at app startup; `/health` still never touches it |

## 2. `POST /api/v1/message` orchestration (T18)

`backend/app/routes.py`'s `message` route, declared as a plain **sync** `def` (not `async def`) —
resolves S06's former G-S06-3. Every downstream call (S05's Groq/Gemini `httpx.post`, S06/S09/S10's
`supabase-py` calls) is already synchronous; FastAPI runs a sync `def` route in its own thread pool
automatically, so nothing here risks blocking the event loop, and there is no `await`/
`run_in_threadpool` boilerplate to write or explain (D-S04-3). `UploadFile.size`/`.content_type` are
plain, non-async attributes already populated by the time the route runs (confirmed against the
installed FastAPI — its own `UploadFile` docstring recommends exactly this for sync routes), so even
the audio checks below need no `await`.

Numbered steps mirror the mock's own `_decide` structure (`backend/mock/app.py`) wherever possible.

1. **Validate input.** `api.check_message_inputs(text=text, has_audio=audio is not None, lat=lat,
   lng=lng)` — any failure → `400 INVALID_INPUT`. Route-level FastAPI `Form`/`File` declarations
   (UUID4, `lat`/`lng` ranges) mirror the mock's exactly. If `audio is not None`:
   `api.normalise_content_type(audio.content_type) not in api.ACCEPTED_AUDIO_TYPES` → `415
   UNSUPPORTED_AUDIO`; `audio.size > api.AUDIO_MAX_BYTES` → `413 AUDIO_TOO_LARGE` (using `.size`, not
   `await audio.read()` — same check, no async needed). **If audio passes both checks, T18 still
   cannot process it — S12 doesn't exist (T26) — so it raises `503 SERVICE_UNAVAILABLE`** (D-S04-4).
   This is temporary: `backend/tests/contract/test_message.py`'s only unmarked (non-`mock_only`)
   audio tests are the 415/413 cases, so this doesn't break the shared contract suite; the
   `mock_only`-marked transcript tests are already skipped against the real backend.
2. **Dedupe on `message_id`.** `stored = session.find_stored_response(session_id, message_id)`
   (S06). Found → `stored.model_copy(update={"duplicate": True})`, returned immediately — nothing
   past this point runs.
3. **Load or create session.** `row = session.get_or_create_session(session_id)` (S06). Owns the
   30-minute timeout (S01 §8, D-A2) — an expired session resets under the same ID, current message
   still processed, never a citizen-facing error.
4. **Command check.** *(Amended by S20/T28: this check now runs after step 5, on the transcript for
   audio, so a spoken `cancel`/`restart` works. Audio is stored and `transcript` returned.)*
   `command = api.parse_command(effective_text)`, before anything reaches the Turn Engine
   (S01 D-A3):
   - `cancel` → `action=cancelled`, `reply_text` = the same Hindi copy the mock uses
     (`REPLY_CANCELLED`, duplicated here rather than imported from `mock/` — see D-S04-6).
     `SessionUpdate(collected_fields={}, awaiting_confirmation=False, lat=None, lng=None,
     status=SessionStatus.CANCELLED)` (S06 RULES §3: the caller clears fields when setting a
     terminal status). Skip to step 8.
   - `restart` → `action=ask`, `ask_for=None`, `reply_text` = the mock's `REPLY_RESTART` copy.
     `SessionUpdate(collected_fields={}, awaiting_confirmation=False, lat=None, lng=None,
     status=SessionStatus.ACTIVE)` — **`lat`/`lng` are cleared too**, not just `collected_fields`
     (D-S04-5): GPS is functionally part of the collected complaint (D-S07-3 treats it as satisfying
     `location`), so a real "start over" clears it along with everything else; `service_id` is left
     as `row.service_id` (S01 D-A3: "not the session"). Skip to step 8.
   - Neither → continue to step 6.
5. **Audio → transcript.** Never reached — audio already short-circuited at step 1 (D-S04-4). Kept
   as a numbered placeholder so this section's step numbers still line up with §4's error-mapping
   table and with S12/T26, which will insert real behavior here later.
6. **Turn Engine.** Skipped if `text` is `None`/blank and no GPS-only shortcut applies at the S05
   layer anyway (S05 §BEHAVIOR 1 already handles that internally — T18 just always calls it):
   ```
   state = turn_engine.SessionState(row.service_id, row.collected_fields, row.awaiting_confirmation)
   recent = session.get_recent_messages(session_id)
   turn_result = turn_engine.run_turn(
       session=state, specs=request.app.state.specs, text=text, lat=lat, lng=lng,
       recent_messages=recent,
   )
   ```
   `TurnEngineUnavailable` → `503 SERVICE_UNAVAILABLE`.
7. **Validate.**
   ```
   snapshot = validator.SessionSnapshot(row.service_id, row.collected_fields,
                                         row.awaiting_confirmation, row.lat, row.lng)
   result = validator.apply(specs=request.app.state.specs, session=snapshot,
                             turn_result=turn_result, lat=lat, lng=lng)
   ```
   `result.action` (S07's own `ValidatedAction`, not S01's `Action` — D-S07-5) drives what happens
   next:
   - `ask`/`confirm`/`out_of_scope` → map 1:1 to the same-named S01 `Action` (the enum *values*
     match exactly — `schemas.Action(result.action.value)`), `ask_for`/`reply_text`/`summary` copied
     straight from `result`. `SessionUpdate(collected_fields=result.collected_fields,
     awaiting_confirmation=result.awaiting_confirmation, lat=lat or row.lat, lng=lng or row.lng,
     status=SessionStatus.ACTIVE)` — `lat`/`lng` carry forward from the session row when this turn
     didn't send new ones (D-S07-3: GPS persists once given). Skip to step 8.
   - `ready_to_submit` → continue to step 7a.
8. (renumbered from S04's original 7a) **Create ticket.**
   ```
   spec = request.app.state.specs[result.service_id]
   original_text = "; ".join(str(v) for v in result.summary.values())
   ticket = ticketing.create_ticket(
       session_id=session_id, spec=spec, validated_fields=result.collected_fields,
       lat=lat, lng=lng, original_text=original_text, audio_path=None,
   )
   ```
   `original_text` resolves S10's former G-S10-1 (D-S04-7): built from `result.summary` — the same
   Hindi display values S07 already computed for the confirmation step — rather than trying to pick
   out "the" original message across a multi-turn conversation, which has no single well-defined
   answer once corrections happen. `action=submitted`, `reply_text = f"आपकी शिकायत दर्ज हो गई है।
   शिकायत क्रमांक: {ticket.complaint_id}।"` (matches S01's own example and the mock's `_submitted`
   format exactly). `SessionUpdate(collected_fields={}, awaiting_confirmation=False, lat=None,
   lng=None, status=SessionStatus.COMPLETED)` (S01 §8: state cleared after submission).
9. **Persist.** `input_type = InputType.TEXT if text is not None else InputType.LOCATION` (audio
   never reaches here — D-S04-4; S01 D-A8's own term for a GPS-only turn is "location-only", which
   is exactly when `text is None`). `session.save_turn(session_id=session_id, message_id=message_id,
   input_type=input_type, text=text, transcript=None, audio_path=None, response=response,
   session_update=session_update)` (S06) — writes the `messages` row (which step 2 will return on a
   retried `message_id`) and updates `sessions` in that order (S06 D-S06-2).
10. **Respond.** Return the `MessageResponse` built in whichever of steps 4/7/8 produced it,
    `duplicate=false`.

## 3. Interfaces called — resolved (closes former G-S04-1)

| Spec | Module | Function | Input | Output |
|---|---|---|---|---|
| S05 Turn Engine | `app.turn_engine` | `run_turn` | `SessionState`, `specs: dict[str, ServiceSpec]`, `text`, `lat`/`lng`, `recent_messages` | `TurnResult` (`service_id`, `fields`, `confirmed`); raises `TurnEngineUnavailable` |
| S06 Session Manager | `app.session` | `get_or_create_session`, `find_stored_response`, `get_recent_messages`, `save_turn` | see `docs/specs/S06-session-manager.md` | `Session`; `MessageResponse \| None`; `list[Message]`; `None` |
| S07 Validator | `app.validator` | `apply` | `specs`, `SessionSnapshot`, `TurnResult`, `lat`/`lng` | `ValidationResult` (`service_id`, `collected_fields`, `awaiting_confirmation`, `action`, `ask_for`, `reply_text`, `summary`) |
| S10 Ticket + routing | `app.ticketing` | `create_ticket` | `session_id`, `spec`, `validated_fields`, `lat`/`lng`, `original_text`, `audio_path` | `schemas.Ticket`; raises on any non-confidence failure |
| S12 Voice | — | — | Not called by T18 at all (D-S04-4). Audio input gets `503` until T26 lands | — |

## 4. Error mapping

| Situation | Result |
|---|---|
| Step 1 fails (bad input) | `400 INVALID_INPUT` |
| Step 1: unsupported/oversized audio | `415 UNSUPPORTED_AUDIO` / `413 AUDIO_TOO_LARGE` |
| Step 1: otherwise-valid audio (S12 doesn't exist yet) | `503 SERVICE_UNAVAILABLE` (D-S04-4) |
| Step 6: `TurnEngineUnavailable` (both LLM providers failed) | `503 SERVICE_UNAVAILABLE` |
| Step 7: a Turn Engine field value fails spec validation | **not an error** — dropped, field stays missing, normal `ask` (S03 TURN RULES #4, already handled inside `validator.apply`) |
| Step 8: ticket creation fails (DB error, `JurisdictionError`) | `500 INTERNAL_ERROR` — routing confidence itself is never a failure, it's `needs_review` |
| Anything unhandled | `500 INTERNAL_ERROR` via `mock/errors.py`'s existing catch-all |
| Any of the above | `reply_text` is always citizen-safe (S01 §9 rule 3) — the catch-all already guarantees this for `500`s |

`action = error` (S01 D-A6, empty/unusable transcript) never occurs in T18 today, since audio never
reaches transcription (D-S04-4) — it becomes relevant once T26 adds real ASR.

## 5. Timeouts (PROJECT.md §7, S01 G-API-4)

| Call | Budget | On expiry |
|---|---|---|
| LLM (Groq or Gemini, whichever is primary) | ~6 s (S05 `PROVIDER_TIMEOUT_SECONDS`) | Fall back to the other |
| Fallback provider | same budget as primary | `503 SERVICE_UNAVAILABLE` |
| ASR (Sarvam) | ~8 s | Not reached yet (T26) |

## ACCEPTANCE

**T07 (app setup) — done:**
- [x] `main.py` boots and serves `GET /health` with no DB/LLM/ASR calls, matching S01 §6 exactly
- [x] A broken `specs/*.yaml` stops startup (via S03's `load_specs`), not the first request
- [x] Missing `ALLOWED_ORIGINS` stops startup with a message naming the var

**T18 (message orchestration):**
- [ ] The contract tests in `backend/tests/contract/` (written against the mock) pass unchanged
      against `main.py` when run with `CONTRACT_TARGET=real`, excluding `mock_only`-marked tests
- [ ] Repeated `message_id` returns the stored response with only `duplicate` changed, and causes no
      second Turn Engine/ticket call (verify via call count, not just the response body)
- [ ] `cancel` and `restart` never reach the Turn Engine (verify via call count); also when spoken (S20)
- [ ] Both LLM providers down → `503 SERVICE_UNAVAILABLE`, not a `500`
- [ ] A Turn-Engine-proposed field value outside the spec's allowed values is dropped, not stored,
      and the field is re-asked
- [ ] Scenario 3 (PROJECT.md/S01 §10.2): issue + location in one message → `action=confirm`
      directly, no intermediate `ask`
- [ ] Scenario 7: GPS in a pilot ward → `action=submitted`, `ticket.office.level="ward"`
- [ ] Scenario 8: unknown location → `ticket.office.level="district"`, `ticket.status=needs_review`
- [ ] Scenario 9: officer sets "In progress" on a real ticket → `GET /status` (T19) reflects it
- [ ] Scenario 10: two concurrent sessions never share state (S06 RULES §1 already guarantees this
      structurally — verify with two real `session_id`s in one test)
- [ ] Any audio submission → `503 SERVICE_UNAVAILABLE` (temporary, until T26), not a `500` or a hang

## DECISIONS

| # | Decision | Reason |
|---|---|---|
| D-S04-1 | `SPECS_DIR` fixed relative path, no env var | Repo layout is fixed for the pilot |
| D-S04-2 | No Supabase client in T07; built lazily by S06/S09/S10 on first use | T07's own acceptance never touches the DB |
| D-S04-3 | The real `/message` route is a plain sync `def`, not `async def` | Every downstream call (S05/S06/S09/S10) is already synchronous; FastAPI thread-pools a sync `def` route automatically, avoiding `run_in_threadpool` boilerplate everywhere — resolves S06's former G-S06-3 |
| D-S04-4 | Any audio submission that passes type/size checks still gets `503 SERVICE_UNAVAILABLE` | S12 (T26) doesn't exist yet; `503` is the honest "this feature isn't available right now" code (S01 already uses it for provider outages) rather than misusing `415`/`413` for otherwise-valid audio |
| D-S04-5 | `restart` clears `lat`/`lng` in addition to `collected_fields` | GPS functionally satisfies the `location` field across turns (D-S07-3), so "start over" should reset it too, not leave a stale location half-applied to a fresh complaint |
| D-S04-6 | `cancel`/`restart` reply text is duplicated in `routes.py` from `mock/app.py`'s `REPLY_CANCELLED`/`REPLY_RESTART`, not imported | `routes.py` (real backend) importing strings from `mock/` would be a backwards dependency; if a third consumer of this copy ever appears, it should move to a shared module then, not now |
| D-S04-7 | `original_text` (S10's former G-S10-1) is built by joining `result.summary`'s values — S07's already-computed Hindi confirmation summary — not by reconstructing raw message history | A multi-turn conversation with corrections has no single well-defined "original" message; the validated summary is always available, always accurate to what was actually confirmed, and requires no extra DB query |

## OPEN

| ID | Item | Needed by |
|---|---|---|
| G-S04-4 | Audio duration check (≤ 60 s) placement — moot until T26, since audio is fully rejected before that matters today | Before T26 |
| G-S04-8 | `routes.py`'s duplicated cancel/restart copy (D-S04-6) should move to a shared module if the website or dashboard ever needs the same strings | If/when a third consumer appears |
