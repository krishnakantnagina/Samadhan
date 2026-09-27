# S06 — Session Manager
Implements: T14 (`backend/app/session.py`, `backend/app/db.py`) · Used by: T18 (S04 §2 steps 2, 3, 8)
· Depends on: S01 API contract (session/idempotency rules, §8), S02 DB schema (`sessions`,
`messages`), S04 orchestration (calling contract), S05 Turn Engine (`Message`, `SessionState` shapes
this module must satisfy) · Version: v1 · Status: Draft

## PURPOSE
Owns the `sessions` and `messages` tables (S02): creating/loading a session with the 30-minute
timeout rule (S01 §8, D-A2), the `(session_id, message_id)` dedupe lookup (S01 §8, S04 §2 step 2),
recent conversation history for the Turn Engine (S05), and the single write at the end of a turn
(S04 §2 step 8). This spec also resolves S04 §3's `[DECIDE]` on the Supabase client (sync vs.
async) and step 2's `[DECIDE]` on which module owns the dedupe lookup.

## SCOPE
`backend/app/session.py` (S06 proper) and `backend/app/db.py` (a small shared Supabase client
factory — new, but needed now since T14 is the first ticket touching the database; T16/T17 reuse it
rather than each building their own). Does not touch `tickets`, `offices`, or `routing_corrections`
(S09/S10), does not resolve jurisdiction, does not decide the citizen-facing `action`, and does not
handle audio storage paths beyond storing whatever string it's given (S12/T26's job to produce it).

## CONFIG
`app/config.py` gains `get_supabase_config() -> SupabaseConfig` (`url`, `service_key`), reading
`SUPABASE_URL` and `SUPABASE_SERVICE_KEY` — both required, raising `RuntimeError` naming the missing
var, same pattern as `get_allowed_origins`/`get_llm_config`. These become required at import time
once T14 lands (S04 §1 already reserves this). `SUPABASE_ANON_KEY` is not read by the backend at
all — the core always uses the service key (S02 RULES §2); anon key is the dashboard/front-end's.

`app/db.py`: `get_client() -> Client` — a cached (`functools.lru_cache`) `supabase-py` client built
from `get_supabase_config()`. One client per process, reused by every call in this spec and by
T16/T17 later.

## DATA TYPES (`app/session.py`)
- `SessionStatus` (StrEnum): `active` · `completed` · `cancelled` · `expired` — mirrors S02's
  `session_status` enum exactly. Not shared with `app/schemas.py`: no S01 response field ever
  carries session status (see DECISIONS D-S06-4).
- `InputType` (StrEnum): `text` · `audio` · `location` — mirrors S02's `messages.input_type` CHECK.
- `Session` (dataclass): `id: uuid.UUID`, `status: SessionStatus`, `service_id: str | None`,
  `collected_fields: dict[str, Any]`, `awaiting_confirmation: bool`, `lat: float | None`,
  `lng: float | None`, `created_at: datetime`, `last_active_at: datetime`. One-to-one with a
  `sessions` row.
- `SessionUpdate` (dataclass): `collected_fields: dict[str, Any]`, `awaiting_confirmation: bool`,
  `lat: float | None`, `lng: float | None`, `status: SessionStatus = SessionStatus.ACTIVE` — what a
  turn leaves the session looking like; passed into `save_turn` by the caller (T18).

`main.py` (T18) builds a `turn_engine.SessionState` directly from the `Session` this module returns
(`service_id`, `collected_fields`, `awaiting_confirmation` — three field copies) rather than S06
exposing an adapter function; not enough surface to justify importing `turn_engine` from `session.py`
just for that.

## FUNCTIONS

### `get_or_create_session(session_id: uuid.UUID) -> Session`
Resolves S04 §2 step 3 and S01 §8/D-A2 exactly. Reads the `sessions` row for `session_id`:
- **No row exists** — insert one with every column at its S02 default (`status=active`,
  `service_id=NULL`, `collected_fields={}`, `awaiting_confirmation=false`, `lat=NULL`, `lng=NULL`),
  `last_active_at = now()`. Return it. This write must happen eagerly (not deferred to `save_turn`)
  because `messages.session_id` is a foreign key — a row must exist before step 8 can insert a
  message against it.
- **Row exists, `now() - last_active_at > 30 minutes`** — the session is stale (S01 D-A2). Update it
  back to the same defaults as the "no row" case (keeping `id` and `created_at`), `last_active_at =
  now()`. Return the refreshed `Session`. The **current message is still processed** under the same
  `session_id` — this must never surface as a citizen-facing error (S01 D-A2, S04 §2 step 3).
- **Row exists, not stale** — return it as read, unmodified. No write. (`last_active_at` is bumped
  once, at the end of the turn, by `save_turn` — not here, to avoid a second write per request.)

Staleness is computed from `last_active_at` alone, every time — never from a stored
`status = 'expired'` value (see DECISIONS D-S06-4). A row whose `status` is `completed` or
`cancelled` but is **not** stale is returned as-is, not specially reset here: by RULES §3, whoever
set that status already cleared the row's fields in the same write, so it is already "fresh" content
under a non-fresh label — reusable for a new complaint on the next message (S01 §8: "the same
`session_id` may be reused").

### `find_stored_response(session_id: uuid.UUID, message_id: uuid.UUID) -> schemas.MessageResponse | None`
Resolves S04 §2 step 2 (previously `[DECIDE]`). Looks up the `messages` row by its PK
`(session_id, message_id)`. Found → parse its stored `response` JSONB back into a
`schemas.MessageResponse` and return it (caller sets `duplicate = True` on a copy before responding
— S06 returns the response exactly as stored, S01 §8: "the stored response unchanged except
`duplicate = true`"). Not found → `None`. Read-only; never touches ASR, the LLM, or `tickets`.

### `get_recent_messages(session_id: uuid.UUID, limit: int = 4) -> list[turn_engine.Message]`
Resolves the "last ~4 messages" input S05 needs (PROJECT.md §4; S05 INPUT table: "Up to the last 4
rows for this session, oldest first"). Fetches the last `limit` **rows** from `messages` for this
session (order by `created_at` desc, then reversed to oldest-first), and unrolls each row into up to
two `turn_engine.Message` entries in chronological order:
- citizen side: `role="citizen"`, `text = row.text or row.transcript`. Omitted entirely if both are
  `None` (a GPS-only turn has nothing to say on the citizen side).
- bot side: `role="bot"`, `text = row.response["reply_text"]`. Always present — `reply_text` is
  never empty per S01 §4.2.

Up to 8 `Message` entries for `limit=4`. Read-only.

### `save_turn(*, session_id, message_id, input_type, text, transcript, audio_path, response, session_update) -> None`
Resolves S04 §2 step 8, the single write point at the end of a turn. Two writes, **in this order**:
1. **Insert** into `messages`: `session_id`, `message_id`, `input_type`, `text`, `transcript`,
   `audio_path` (whichever apply, others `NULL`), `response` = the full `schemas.MessageResponse`
   (`.model_dump(mode="json")`) as JSONB.
2. **Update** the `sessions` row (`collected_fields`, `awaiting_confirmation`, `lat`, `lng`,
   `status`, `last_active_at = now()`) from `session_update`.

Messages-insert **before** sessions-update — see DECISIONS D-S06-2 for why the order matters. A PK
conflict on the `messages` insert (another concurrent request already wrote this exact
`(session_id, message_id)` row) is caught and treated as a benign no-op, not raised — see RULES §5.

## RULES
1. No process-wide mutable session cache. Every function takes `session_id` and round-trips to the
   database; nothing is kept in a module-level variable between calls. This is what makes scenario
   10 ("two browsers at once → sessions never mix", S01 §10.2) hold structurally, not by convention.
2. `SessionStatus.EXPIRED` is a defined enum value (matches S02) that this module never writes —
   staleness is always a live computation on `last_active_at`, not a stored state (D-S06-4).
3. Whoever calls `save_turn` with `session_update.status` set to `completed` or `cancelled` is
   responsible for also clearing `collected_fields`/`awaiting_confirmation`/`lat`/`lng` in that same
   `SessionUpdate` (S01 §8: "conversation state is cleared"). `save_turn` writes exactly what it's
   given; it does not infer or auto-clear anything from `status`.
4. `messages` is written before `sessions` in `save_turn`, so a crash between the two leaves the
   dedupe guarantee intact even though session state may lag by one turn (RULES §5 / D-S06-2).
5. A unique-constraint violation on the `messages` insert is swallowed, not raised — first writer
   wins, the second writer's identical row was redundant, not an error.
6. Supabase/network errors are not caught or wrapped anywhere in this module. They propagate to
   `main.py`'s existing catch-all (`app/errors.py`) → `500 INTERNAL_ERROR` (S04 §4). Unlike S05's
   Groq/Gemini handling, S06 has no fallback provider to try — the database is infrastructure the
   team controls, not a third-party voice/LLM API prone to the kind of transient failure S01 D-A6
   was written around.

## ERRORS
| Situation | Result |
|---|---|
| Unknown `session_id` | `get_or_create_session` creates it; not an error |
| Session stale (> 30 min) | `get_or_create_session` resets it; current message still processed, no citizen-facing error (S01 D-A2) |
| Duplicate `(session_id, message_id)` on read | `find_stored_response` returns the stored response; caller marks `duplicate=true` |
| Duplicate `(session_id, message_id)` on write (race, RULES §5) | `save_turn` treats it as a no-op |
| Supabase unreachable / any other DB error | Propagates uncaught → `500 INTERNAL_ERROR` (S04 §4) |

## OUT OF SCOPE
- Full request-level concurrency control that would stop two genuinely simultaneous requests
  carrying the same `message_id` from both running an entire turn (Turn Engine, validation, possibly
  ticket creation) before either's `messages` row commits — see G-S06-1.
- Anything about `tickets`, `offices`, `routing_corrections`, jurisdiction, or ticket status (S09,
  S10; dashboard).
- Audio storage itself (S12/T26 produces `audio_path`; S06 only stores the string).
- Session/message retention or cleanup jobs (no such job anywhere in M1 scope, PROJECT.md §2).

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S06-1 | `supabase-py` (sync client, `create_client`), matching `dashboard/pyproject.toml`'s existing `supabase>=2.31.0` pin | Resolves S04 D-S04-2's deferred sync/async question; reuses the pattern already proven in `docs/plans/T06-plan.md`'s build log ("T14 uses supabase-py with SUPABASE_URL/SUPABASE_SERVICE_KEY"), and matches T12's own choice of plain sync calls (`httpx.post`, not an async client) — one concurrency model across the backend, easier to explain to judges (CLAUDE.md §9 rule 6) |
| D-S06-2 | `messages` insert happens before the `sessions` update inside `save_turn` | If the process dies between the two writes, a retried `message_id` must still hit the dedupe path (S01 §8's whole point: no double ticket on a network retry) — a stale-but-present session row is a minor UX hiccup (one re-asked question), not a correctness bug. The reverse order risks the opposite: a retry that finds no `messages` row would reprocess the turn from scratch, defeating the dedupe guarantee entirely |
| D-S06-3 | `save_turn` never auto-clears fields on a status change; the caller must pass a fully-formed `SessionUpdate` | Keeps S06 a dumb, predictable storage layer — business logic (when a turn counts as "submitted" or "cancelled") belongs to T18/S10, not here (mirrors S04 §3's split between orchestration and each module's own internals) |
| D-S06-4 | `SessionStatus` lives only in `app/session.py`, not `app/schemas.py`; `expired` is defined but never written, staleness is always computed live | No S01 response field ever carries session status, so it isn't part of the API contract (S01's own scope). S02 RULES §3 confirms the dashboard never reads `sessions` at all — nothing outside this module consumes `status`, so keeping it simple (time-based staleness, no extra write) costs nothing |
| D-S06-5 | New `app/db.py` client factory, not folded directly into `session.py` | T14 is the first ticket to touch the database; T16 (jurisdiction) and T17 (ticket + routing) need the same client and should not each build their own `get_supabase_config`/`create_client` wiring |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S06-1 | Two genuinely simultaneous requests with the same `message_id` can both pass the dedupe check (S04 §2 step 2) before either's `messages` row commits, and both run a full turn — including, worst case, both reaching ticket creation (S10). `save_turn`'s PK-conflict handling (RULES §5) only protects the `messages` row itself, not this deeper race. Not fixed here: the real critical section is S10's ticket creation, which doesn't exist yet. Recommend revisiting with a `pg_advisory_xact_lock` on `hashtext(session_id)` (or similar) wrapping the whole per-request turn once S10 (T17) exists, rather than solving it in isolation now | Before T17 lands, or by T31 integration at the latest |
| G-S06-2 | `backend/pyproject.toml` needs `supabase>=2.31.0` added at implementation time (matching `dashboard/pyproject.toml`), plus a README Attribution entry | T14 implementation |
| G-S06-3 | Whether T18's `POST /message` route is declared `def` (FastAPI auto-threadpools it) or `async def` with S05/S06's sync calls explicitly wrapped in `run_in_threadpool`/`anyio.to_thread.run_sync` — S06 itself is sync either way; this only affects whether T18 risks blocking the event loop under concurrent load. Flagged so it isn't silently forgotten, not because it's likely to matter at hackathon-demo traffic levels | T18 implementation |

## ACCEPTANCE
| Item | Covered by |
|---|---|
| TICKETS.md "Users isolated" / S01 §10.2 scenario 10 (two browsers, sessions never mix) | RULES §1 — no shared mutable state, every call keyed by `session_id` |
| Unknown `session_id` → a usable session, not an error | `get_or_create_session`, "no row exists" branch |
| Session idle > 30 min → fresh state under the same ID, current message still processed (S01 D-A2) | `get_or_create_session`, "stale" branch |
| Repeated `message_id` → identical stored response except `duplicate`, no reprocessing (S01 §8) | `find_stored_response` + T18 setting `duplicate=true` on the copy |
| The row a retry returns reflects the final response, not a partial one | `save_turn` inserts `messages` only once the caller has the finished `MessageResponse` in hand |
| After `submitted`/`cancelled`, the same `session_id` is reusable for a new complaint | RULES §3 (caller clears fields) + `get_or_create_session`'s non-special-casing of a fresh-but-labeled-terminal row |
| Turn Engine gets up to 4 turns of history, oldest first | `get_recent_messages` |
