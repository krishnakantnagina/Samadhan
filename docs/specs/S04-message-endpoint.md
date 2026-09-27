# S04 — App Setup & Message Orchestration
Implements: T07 (`backend/app/main.py`), T18 · Used by: T19 (status, same app) · Depends on: S01 API contract, S02 DB schema, S03 service spec format · Version: v1 · Status: Draft

## PURPOSE
Wires the real backend together: the FastAPI app itself (T07) and the step-by-step handling of
`POST /api/v1/message` (T18). This spec owns orchestration only — *what calls what, in what order,
with which fallback*. The Turn Engine (S05), Session Manager (S06), Validator (S07), Ticket +
routing (S10), and Voice (S12) each own their own internals; S04 only names the function each one
must expose so `main.py` can call it. Those specs are not written yet — every interface below is
marked `[DECIDE]` until its own spec fixes the signature.

## SCOPE
`backend/app/main.py` (real API) and the body of the `/api/v1/message` route. `GET /health` and
`GET /api/v1/status/{complaint_id}` are named for completeness (T19) but their internals belong to
S11, not here. The mock (`backend/mock/app.py`, T08) is unaffected — it keeps its canned rules and
stays available for the website and for contract tests. `main.py` reuses `app/schemas.py` and
`app/errors.py` verbatim; it does not fork them the way the mock does not, either.

## 1. App setup (T07)

| Piece | Rule |
|---|---|
| Entry point | `backend/app/main.py`, `app = FastAPI(title="Samadhan API", version=api.CONTRACT_VERSION)` |
| Config | Read directly from `os.environ` at import time, same pattern as `mock/app.py`'s `_origins` line — no new config-loading dependency unless one is already needed for another ticket. Required at startup for T07: `ALLOWED_ORIGINS` only. `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `LLM_PROVIDER`, `GROQ_API_KEY`/`GEMINI_API_KEY`, `SARVAM_API_KEY` are read as optional at this stage (present in `.env.example` but not enforced) — each becomes required at import time once the ticket that needs it lands (T14 for Supabase, T12 for the LLM vars, T26 for Sarvam). Missing `ALLOWED_ORIGINS` → fail fast at import, not on first request |
| CORS | `CORSMiddleware`, `allow_origins` from `ALLOWED_ORIGINS` (comma-separated), `allow_methods=["GET", "POST"]` — identical to the mock (S01 §9 rule 4) |
| Error handlers | `register_error_handlers(app)` from `app/errors.py`, unchanged (S01 §7) |
| `GET /health` | No auth, no DB/ASR/LLM call, returns `api.HealthResponse()` — identical to the mock (S01 §6) |
| Router | Business routes under `/api/v1` (`message`, `status/{complaint_id}`); `/health` stays unprefixed. T07 registers the router with no route bodies yet (or omits `/message`/`/status` entirely until T18/T19) — no `/message` logic in T07 |
| Startup | `app.state.specs = service_spec.load_specs(SPECS_DIR)` (S03) via FastAPI `lifespan`, so a broken YAML stops the process before it serves traffic, not on the first `/message` call. **Decided:** `SPECS_DIR = Path(__file__).resolve().parents[2] / "specs"` — fixed path relative to `main.py` (`backend/app/main.py` → repo `specs/`), no env var, since the repo layout is fixed for the pilot |
| DB / storage client | **Decided:** not built in T07. `/health` must never call the DB regardless (S01 rule 5), and nothing else in T07's scope needs one. The Supabase client (sync vs. async) is T14's (Session Manager, S06) concern; `supabase-py` is not a T07 dependency |

## 2. `POST /api/v1/message` orchestration (T18)

Numbered steps below are the order `main.py`'s route body follows. Each step either short-circuits
with a response/error or hands its output to the next step.

1. **Validate input.** Reuse `api.check_message_inputs(...)` (already in `schemas.py`, already used
   by the mock). Route-level FastAPI form/type checks (UUIDs, `lat`/`lng` ranges) fire first via
   `MessageRequest`/`Form(...)` the same way the mock declares them. Any failure → `400 INVALID_INPUT`
   (S01 §7). Audio content-type check (`ACCEPTED_AUDIO_TYPES`) and byte-size check
   (`AUDIO_MAX_BYTES`) run here too, same as the mock. Audio **duration** (≤ 60 s) cannot be checked
   yet without decoding — open per G-API-8; when the FFmpeg step (S12) lands, a duration check
   belongs here or just after transcoding, whichever S12 measures first.
2. **Dedupe on `message_id`.** Look up `(session_id, message_id)` in `messages` (S02, PK on that
   pair). Found → return the stored `response` JSONB unchanged except `duplicate = true`. Nothing
   past this point runs: no ASR, no LLM, no ticket (S01 §8). `[DECIDE]` exact lookup call — depends
   on whichever thin DB-access helper S06/S10 introduce; `main.py` should not hold raw SQL/Supabase
   query calls inline if a helper already exists for `messages`.
3. **Load or create session.** `session = session_manager.get_or_create_session(session_id)` (S06,
   `[DECIDE]`). Session Manager owns the 30-minute timeout rule (S01 §8, D-A2): an expired
   `session_id` gets a fresh session under the same ID, and the current message is still processed
   — this must not surface as an error to the citizen.
4. **Command check.** Before anything reaches the Turn Engine, `api.parse_command(text)` — `cancel`
   → clear session state, `action = cancelled`, skip to step 8. `restart` → clear collected fields
   only (not the session), `action = ask`, skip to step 8. This matches the mock's `_decide` and S01
   D-A3: commands are backend-recognised text, never sent to the LLM.
5. **Audio → transcript.** If `audio` is present: `transcript = voice.transcribe(audio_bytes,
   content_type)` (S12, `[DECIDE]`). Internally: FFmpeg → 16 kHz mono WAV → Sarvam Saarika ASR →
   on failure/timeout (~8 s), fallback Groq Whisper. Original audio and transcript are both kept
   (PROJECT.md §7, §13) — `voice.transcribe` or the caller must persist `audio_path` before step 8's
   message write, not after. Both providers failing → `503 SERVICE_UNAVAILABLE` (S01 §7, D-A6: this
   is a provider outage, not a bad recording). An empty or unintelligible transcript is **not** an
   exception: it becomes `action = error` in step 8 with `transcript` set to whatever was returned
   (S01 §4.3, D-A6).
6. **Turn Engine.** `result = turn_engine.run_turn(session, spec, text=text or transcript, lat=lat,
   lng=lng)` (S05, `[DECIDE]`). Input: session state (`service_id`, `collected_fields`,
   `awaiting_confirmation`), the active `ServiceSpec` (S03) — or all loaded specs if `service_id` is
   still unset — and the last ~4 messages for context (PROJECT.md §7). One LLM call, strict JSON
   (Groq primary → Gemini fallback, ~6 s timeout each). Output is **untrusted**: a proposed action,
   any field values the LLM extracted, and whether the citizen's turn reads as a confirmation. Both
   providers failing → `503 SERVICE_UNAVAILABLE`. Malformed/unparseable JSON from both → treated as
   step 6 failure, same `503`, not `action = error` (that code path is for citizen-facing ambiguity,
   not a broken provider response).
7. **Validate.** `validated = validator.apply(spec, session, result)` (S07, `[DECIDE]`). Every field
   value the Turn Engine proposed is checked against its spec type rule (S03 FIELDS table); anything
   outside `values`/`min`/`max`/`max_length`, or naming a field not in the spec, is dropped silently
   and that field stays missing (S03 TURN RULES #4) — this must not become `action = error`, it just
   means another `ask`. The validator decides the actual `action` returned to the citizen:
   - Still-missing required field → `ask`, `ask_for = <field name>`, question in the citizen's
     language (S03 TURN RULES #1).
   - All required fields present, citizen has not yet confirmed → `confirm`, `summary` built from
     `spec` field labels + validated values (S01 §4.2, §4.4 note).
   - All required fields present **and** the Turn Engine read this turn as a confirmation → proceed
     to step 7a (ticket creation) before responding.
   - Turn Engine flagged the message as not matching any loaded service → `out_of_scope`,
     `reply_text` from that service's `out_of_scope.reply` (S03) — `[DECIDE]` which service's reply
     is used when more than one is loaded; M1 ships one, so moot for now (S03 OPEN).
   7a. **Create ticket** (only reached from the confirm-and-confirmed branch above).
       `ticket = ticketing.create_ticket(session, spec, validated_fields, lat, lng)` (S10,
       `[DECIDE]`). S10 owns jurisdiction resolution internally (GPS-to-ward or fuzzy name match,
       confidence scoring, `min_confidence`/`max_match_distance_km` from the spec's `routing` block)
       and returns a fully formed `Ticket` (S01 §4.4) with `status = new` or `needs_review` +
       district office already decided (S03 TURN RULES #6, PROJECT.md §7 step 7). `main.py` does not
       touch jurisdiction logic directly. `action = submitted`.
8. **Persist.** Insert one row into `messages` (S02): `session_id`, `message_id`, `input_type`,
   `text`/`transcript`/`audio_path` (whichever apply), the full `MessageResponse` as `response`
   JSONB. Update `sessions.collected_fields`, `awaiting_confirmation`, `last_active_at` (and
   `lat`/`lng` if sent) to whatever step 3–7 left them at. This is the row step 2 will return on a
   retried `message_id`, so it must be written **after** the response body is final, not before.
9. **Respond.** Return the `api.MessageResponse` built in whichever step produced it (4, 5, 7, or
   7a), `duplicate = false`. Every field always present per S01 §3 ("absent values are null, never
   omitted") — `main.py` builds the model the same way the mock does, not a hand-rolled dict.

## 3. Interfaces called (signatures owned by their own spec; named here so T18 has something to call against)

| Spec | Module (`[DECIDE]`) | Function (`[DECIDE]`) | Input | Output |
|---|---|---|---|---|
| S05 Turn Engine | `app.turn_engine` | `run_turn` | session state, active `ServiceSpec`(s), text, `lat`/`lng`, last ~4 messages | proposed action + raw (untrusted) field values + confirmation flag |
| S06 Session Manager | `app.session` | `get_or_create_session` | `session_id` | `Session` (creates fresh one if unknown or expired, S01 D-A2) |
| S07 Validator | `app.validator` | `apply` | `ServiceSpec`, `Session`, Turn Engine result | validated fields, computed `action`, `ask_for`, `summary` |
| S10 Ticket + routing | `app.ticketing` | `create_ticket` | `Session`, `ServiceSpec`, validated fields, `lat`/`lng` | `api.Ticket` with office + status already resolved |
| S12 Voice | `app.voice` | `transcribe` | raw audio bytes, content type | transcript string (possibly empty), or raises on total provider failure |

None of these five modules exist yet; T18 cannot be implemented until at least stub versions of
each do. This table is the contract T18's code is written against — when S05/S06/S07/S10/S12 are
written, their function names/signatures should match this table or this table should be corrected
to match them (whichever spec lands first wins; tell the other).

## 4. Error mapping

| Situation | Result |
|---|---|
| Step 1 fails (bad input, unsupported/oversized audio) | `400 INVALID_INPUT` / `413 AUDIO_TOO_LARGE` / `415 UNSUPPORTED_AUDIO` — same codes the mock already returns |
| Step 5: ASR primary + fallback both fail/timeout | `503 SERVICE_UNAVAILABLE` |
| Step 5: ASR succeeds but transcript is empty/unusable | **not an error** — `action = error`, HTTP `200`, step 8/9 as normal (S01 D-A6) |
| Step 6: LLM primary + fallback both fail/timeout, or both return unparseable JSON | `503 SERVICE_UNAVAILABLE` |
| Step 7: Turn Engine JSON parses but a value fails spec validation | **not an error** — value dropped, field stays missing, normal `ask` (S03 TURN RULES #4) |
| Step 7a: ticket creation fails for a reason other than routing confidence (e.g. DB write failure) | `500 INTERNAL_ERROR` — routing confidence itself is not a failure, it's `needs_review` |
| Anything unhandled | `500 INTERNAL_ERROR` via the existing catch-all handler in `app/errors.py` |
| Any of the above | `reply_text` is always citizen-safe (S01 §9 rule 3): no stack traces, keys, internal names. The catch-all in `app/errors.py` already guarantees this for `500`; steps 5–7's `action = error` replies must be written in the citizen's language, not a debug string, same as the mock's `REPLY_ERROR` |

## 5. Timeouts (PROJECT.md §7, S01 G-API-4)

| Call | Budget | On expiry |
|---|---|---|
| ASR (Sarvam) | ~8 s | Fall back to Groq Whisper |
| LLM (Groq) | ~6 s | Fall back to Gemini Flash |
| Fallback provider (either) | same budget as primary | `503 SERVICE_UNAVAILABLE` |

Total worst case before a fallback kicks in is additive per G-API-4 (~14 s ASR+LLM before any
fallback); this spec does not change that budget, only names where each timeout applies in the
step list above.

## ACCEPTANCE

**T07 (app setup) — covered by this ticket:**

- [ ] `main.py` boots and serves `GET /health` with no DB/LLM/ASR calls, matching S01 §6 exactly
- [ ] A broken `specs/*.yaml` stops startup (via S03's `load_specs`), not the first request
- [ ] Missing `ALLOWED_ORIGINS` stops startup with a message naming the var (T07's only required var)

**T18 (message orchestration) — not part of T07, listed here for completeness:**

- [ ] The 9 contract tests in `backend/tests/contract/` (written against the mock) pass unchanged
      against `main.py` when run with `CONTRACT_TARGET=real` (per `backend/README.md`)
- [ ] Repeated `message_id` returns the stored response with only `duplicate` changed, and causes no
      second ASR/LLM/ticket call (verify via call count, not just the response body)
- [ ] `cancel` and `restart` never reach the Turn Engine (verify via call count / mock the module)
- [ ] Both LLM providers down → `503 SERVICE_UNAVAILABLE`, not a 500 and not a hung request past
      the ~14 s combined budget
- [ ] An LLM-proposed field value outside the spec's allowed values is dropped, not stored, and the
      field is re-asked

## DECISIONS

| # | Decision | Reason |
|---|---|---|
| D-S04-1 | `SPECS_DIR = Path(__file__).resolve().parents[2] / "specs"`, fixed relative path, no env var (resolves former G-S04-3) | Repo layout is fixed for the pilot; one less required env var to keep in sync across local/deploy |
| D-S04-2 | No Supabase client in T07; deferred to T14 (Session Manager, S06) (resolves former G-S04-2) | T07's own acceptance never touches the DB; picking sync/async now would guess ahead of S06 |

## OPEN

| ID | Item | Needed by |
|---|---|---|
| G-S04-1 | S05/S06/S07/S10/S12 do not exist yet; §3's module/function names are provisional until each spec is written | Before T12/T14/T15/T17/T26 start |
| G-S04-4 | Audio duration check (≤ 60 s) placement: inside S12 after FFmpeg, or a separate `ffprobe` step in `main.py` before handing bytes to S12 (G-API-8) | Before T26 |
