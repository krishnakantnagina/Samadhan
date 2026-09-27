# Plan: T14 — Session manager

Ticket: `docs/TICKETS.md` T14 (owner Dev, depends on T06/T07, done when "Users isolated").
Spec: `docs/specs/S06-session-manager.md`.

**Scope: T14 only.** This plan builds `backend/app/session.py`, the new `backend/app/db.py`, and
`backend/app/config.py`'s Supabase addition. It does **not** wire `session.py` into
`POST /message` — that's T18. `backend/app/main.py` and `backend/app/routes.py` are not touched.

**Decisions this plan assumes (already resolved, see S06 DECISIONS D-S06-1…5):**
- Sync `supabase-py` client, matching `dashboard/pyproject.toml`'s existing pin and T12's own
  sync-`httpx` choice — resolves S04 D-S04-2.
- `messages` insert happens before the `sessions` update inside `save_turn`, so a crash between the
  two still leaves the dedupe guarantee intact.
- Callers own clearing `collected_fields`/`awaiting_confirmation`/`lat`/`lng` when they set
  `status` to `completed`/`cancelled` — `save_turn` never auto-clears.
- `SessionStatus` lives only in `session.py` (not `schemas.py`); staleness is always computed live
  from `last_active_at`, never stored.
- New shared `app/db.py` client factory, since T16/T17 need the same Supabase client later.

**New implementation decisions this plan makes** (S06 stays at the behavior/contract level, not
Python/library mechanics):
- `postgrest.exceptions.APIError` (pulled in transitively by `supabase-py`) is the exception
  `save_turn` catches to detect a `messages` PK conflict (`exc.code == "23505"`, Postgres's
  unique-violation code) — the real exception type, so tests can exercise the catch clause with a
  fake that raises the same class, not a hand-rolled stand-in.
- Every `session.py` function takes an optional `client: Client | None = None` parameter, defaulting
  to `db.get_client()` — the same injectable-seam pattern T12 used for `providers` — so tests supply
  a fake Supabase client and make zero network calls, no real credentials required.
- A `FakeSupabaseClient` test double (in `test_session.py`), backed by two in-memory
  `list[dict]` stores (`sessions`, `messages`), implements only the chained-builder calls
  `session.py` actually makes, including PK-conflict detection on `messages` insert.
- Datetimes from Supabase (ISO 8601 strings) are parsed with `datetime.fromisoformat`; staleness
  compares against `datetime.now(timezone.utc)` — both sides timezone-aware, called out explicitly
  since a naive/aware mismatch raises rather than silently misbehaving.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `backend/app/db.py` | Create | `get_client() -> Client`, `lru_cache`d Supabase client factory (S06 SCOPE, D-S06-5) |
| `backend/app/config.py` | Edit | Add `SupabaseConfig` + `get_supabase_config()` (S04 §1: Supabase vars required once T14 lands) |
| `backend/app/session.py` | Create | `SessionStatus`, `InputType`, `Session`, `SessionUpdate`, `get_or_create_session`, `find_stored_response`, `get_recent_messages`, `save_turn` |
| `backend/tests/test_session.py` | Create | `FakeSupabaseClient` + tests for every S06 function/branch |
| `backend/tests/test_config.py` | Edit | Tests for `get_supabase_config()` |
| `backend/tests/test_db.py` | Create | `get_client()` builds from config, is cached |
| `backend/pyproject.toml` | Edit | Add `supabase>=2.31.0` (matches `dashboard/pyproject.toml`) |
| `README.md` | Edit | Attribution: Supabase (Postgres + Storage, via `supabase-py`) |
| `docs/TICKETS.md` | Edit (last step) | Tick T14 `[x]` |

Not touched: `backend/app/main.py`, `backend/app/routes.py`, `backend/app/turn_engine.py`,
`backend/mock/*`, `backend/tests/contract/*` — T18 wires `session.py` into the real route later;
`turn_engine.py` only needs `SessionState`/`Message`-shaped data, which T18 builds from what
`session.py` returns (three fields copied directly — S06's own note, no adapter function needed).

## 2. Steps, in order

**S1 — `backend/app/config.py`: `SupabaseConfig` + `get_supabase_config()`.**
```python
@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    service_key: str

def get_supabase_config() -> SupabaseConfig:
    return SupabaseConfig(url=_require("SUPABASE_URL"), service_key=_require("SUPABASE_SERVICE_KEY"))
```
Reuses the existing `_require` helper `get_llm_config` already added — no new pattern.

**S2 — `backend/app/db.py`.**
```python
from functools import lru_cache
from supabase import Client, create_client
from app.config import get_supabase_config

@lru_cache
def get_client() -> Client:
    config = get_supabase_config()
    return create_client(config.url, config.service_key)
```

**S3 — `backend/app/session.py`: enums and dataclasses.**
`SessionStatus` (StrEnum: `active`/`completed`/`cancelled`/`expired`), `InputType` (StrEnum:
`text`/`audio`/`location`) — mirror S02's CHECK constraints exactly. `Session` (frozen dataclass:
`id: uuid.UUID`, `status`, `service_id: str | None`, `collected_fields: dict[str, Any]`,
`awaiting_confirmation: bool`, `lat/lng: float | None`, `created_at/last_active_at: datetime`).
`SessionUpdate` (frozen dataclass: `collected_fields`, `awaiting_confirmation`, `lat`, `lng`,
`status: SessionStatus = SessionStatus.ACTIVE`). Private helpers: `_row_to_session(row) -> Session`,
`_default_fields() -> dict` (S02-default column values, no `id`), `_now_iso() -> str`.

**S4 — `get_or_create_session`.**
```python
def get_or_create_session(session_id: uuid.UUID, *, client: Client | None = None) -> Session:
    client = client or get_client()
    existing = (
        client.table("sessions").select("*").eq("id", str(session_id)).maybe_single().execute()
    ).data

    if existing is None:
        row = {"id": str(session_id), **_default_fields(), "last_active_at": _now_iso()}
        inserted = client.table("sessions").insert(row).execute().data[0]
        return _row_to_session(inserted)

    last_active = datetime.fromisoformat(existing["last_active_at"])
    if datetime.now(timezone.utc) - last_active > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
        row = {**_default_fields(), "last_active_at": _now_iso()}
        updated = client.table("sessions").update(row).eq("id", str(session_id)).execute().data[0]
        return _row_to_session(updated)

    return _row_to_session(existing)
```
`SESSION_TIMEOUT_MINUTES = 30` module constant (S01 §8 / PROJECT.md §6).

**S5 — `find_stored_response`.**
```python
def find_stored_response(
    session_id: uuid.UUID, message_id: uuid.UUID, *, client: Client | None = None
) -> schemas.MessageResponse | None:
    client = client or get_client()
    row = (
        client.table("messages")
        .select("response")
        .eq("session_id", str(session_id))
        .eq("message_id", str(message_id))
        .maybe_single()
        .execute()
    ).data
    return None if row is None else schemas.MessageResponse.model_validate(row["response"])
```

**S6 — `get_recent_messages`.**
```python
def get_recent_messages(
    session_id: uuid.UUID, limit: int = 4, *, client: Client | None = None
) -> list[Message]:
    client = client or get_client()
    rows = (
        client.table("messages")
        .select("text,transcript,response")
        .eq("session_id", str(session_id))
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data
    rows.reverse()  # oldest first (S05 INPUT)
    result: list[Message] = []
    for row in rows:
        citizen_text = row["text"] or row["transcript"]
        if citizen_text:
            result.append(Message(role="citizen", text=citizen_text))
        result.append(Message(role="bot", text=row["response"]["reply_text"]))
    return result
```
Imports `Message` from `app.turn_engine` (one-directional: `session.py` → `turn_engine.py`, never
the reverse — `turn_engine.py` is untouched by this ticket).

**S7 — `save_turn`.**
```python
def save_turn(
    *,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    input_type: InputType,
    text: str | None,
    transcript: str | None,
    audio_path: str | None,
    response: schemas.MessageResponse,
    session_update: SessionUpdate,
    client: Client | None = None,
) -> None:
    client = client or get_client()
    message_row = {
        "session_id": str(session_id),
        "message_id": str(message_id),
        "input_type": input_type,
        "text": text,
        "transcript": transcript,
        "audio_path": audio_path,
        "response": response.model_dump(mode="json"),
    }
    try:
        client.table("messages").insert(message_row).execute()
    except APIError as exc:
        if exc.code != UNIQUE_VIOLATION:
            raise  # RULES 5: a PK conflict here means another request already wrote this row

    client.table("sessions").update(
        {
            "collected_fields": session_update.collected_fields,
            "awaiting_confirmation": session_update.awaiting_confirmation,
            "lat": session_update.lat,
            "lng": session_update.lng,
            "status": session_update.status,
            "last_active_at": _now_iso(),
        }
    ).eq("id", str(session_id)).execute()
```
`UNIQUE_VIOLATION = "23505"` module constant. Insert happens before update, unconditionally (D-S06-2).

**S8 — `backend/tests/test_session.py`: `FakeSupabaseClient`.**
Two in-memory stores (`list[dict]` for `sessions`, for `messages`). A small chained-builder fake
supporting exactly the calls S3–S7 make: `.table(name)` → query object; `.select(...)`,
`.eq(col, val)` (accumulates filters), `.order(col, desc=...)`, `.limit(n)`, `.maybe_single()`
(marks single-result mode), `.insert(row)` / `.update(row)` (payload + operation type); `.execute()`
applies filters against the in-memory store and returns an object exposing `.data` (a single dict/
`None` for `maybe_single`, else a list). `.insert()` on `messages` checks the `(session_id,
message_id)` pair against existing rows first and raises `postgrest.exceptions.APIError({"code":
"23505", "message": "duplicate key"})` on a match, mirroring the real Postgres PK.

**S9 — `backend/tests/test_session.py`: tests.**
- `test_get_or_create_session_creates_new` — empty store → returns `Session` with S02 defaults;
  store now has exactly one row.
- `test_get_or_create_session_returns_active_unchanged` — pre-seed a row with recent
  `last_active_at` and non-default `collected_fields` → returned as-is; no `update` call made
  (fake tracks a call log, asserted empty for `sessions`).
- `test_get_or_create_session_resets_stale` — pre-seed `last_active_at` 31 minutes in the past with
  non-default fields → returned `Session` has S02 defaults, same `id`, `last_active_at` bumped.
- `test_get_or_create_session_reuses_completed_row_as_is` — pre-seed `status="completed"`, fields
  already cleared, `last_active_at` recent → returned unchanged, `status` still `"completed"`
  (D-S06-4: no special-casing by status, only by staleness).
- `test_find_stored_response_found` / `test_find_stored_response_not_found`.
- `test_get_recent_messages_unrolls_citizen_and_bot_oldest_first` — 2 seeded rows → 4 `Message`s in
  the right order.
- `test_get_recent_messages_skips_citizen_line_when_no_text` — a GPS-only row (`text`/`transcript`
  both `None`) → only the bot-side `Message` appears for that row.
- `test_get_recent_messages_respects_limit` — 6 seeded rows, `limit=4` → only the last 4 rows'
  worth appear.
- `test_save_turn_writes_message_then_updates_session_in_order` — fake's call log shows `insert
  messages` before `update sessions`; both stores reflect the write.
- `test_save_turn_duplicate_message_insert_is_a_noop` — seed the `messages` row first, call
  `save_turn` with the same `(session_id, message_id)` → no exception, `messages` still has exactly
  one row for that pair, the `sessions` update still runs.

**S10 — `backend/tests/test_config.py` additions.**
Missing `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` each raise naming the var; valid env parses into the
right `SupabaseConfig`.

**S11 — `backend/tests/test_db.py`.**
Monkeypatch `app.db.create_client` to a stub recording its call args; `get_client()` with valid env
calls it once with `(url, service_key)`; a second `get_client()` call does not call `create_client`
again (`lru_cache`) — test clears the cache (`get_client.cache_clear()`) in setup/teardown so it
doesn't leak into other tests.

**S12 — `backend/pyproject.toml`.**
Add `"supabase>=2.31.0"` to `dependencies`, matching `dashboard/pyproject.toml`'s pin exactly.

**S13 — `README.md` Attribution.**
Add to the Backend bullet list: Supabase (Postgres + Storage, via `supabase-py`) — linked, next to
the Groq/Gemini line. (Not added by T06, which only touched the live project and `.env.example`.)

**S14 — Run the suite and lint.**
`cd backend; uv run pytest` (new tests green, all existing ones — contract, spec, config, main,
turn_engine — unaffected) and `uv run ruff check . && uv run ruff format --check .`.

**S15 — Tick it off.**
`docs/TICKETS.md`: T14 `[x]`, once S14 is green.

## 3. Acceptance coverage

| S06 acceptance item | Covered by |
|---|---|
| Two browsers never mix (S01 §10.2 scenario 10) | Structural — no shared state; satisfied by design (every call keyed by `session_id`, nothing cached at module scope), not a directly-runnable "two browsers" test |
| Unknown `session_id` → usable session | S9 `test_get_or_create_session_creates_new` |
| Idle > 30 min → fresh state, same ID | S9 `test_get_or_create_session_resets_stale` |
| Repeated `message_id` → stored response, no reprocessing | S9 `test_find_stored_response_found` (T18 sets `duplicate=true` on the copy — outside this ticket) |
| `messages` written before `sessions` (crash-safety ordering) | S9 `test_save_turn_writes_message_then_updates_session_in_order` |
| Reusable after `submitted`/`cancelled` | S9 `test_get_or_create_session_reuses_completed_row_as_is` |
| Turn Engine gets ≤ 4 turns, oldest first | S9 `test_get_recent_messages_unrolls_citizen_and_bot_oldest_first` + `_respects_limit` |

G-S06-1 (the deeper concurrent-duplicate-request race) is explicitly **not** covered by any test
here — S06 itself defers it to T17/T31, and this plan doesn't relitigate that.

## 4. New libraries
`supabase>=2.31.0` (pulls in `postgrest`, `gotrue`, `storage3`, `realtime` transitively — same set
already proven in `dashboard/.venv`). `README.md` Attribution updated (S13).

## 5. How existing tests stay unaffected
`backend/mock/*`, `backend/tests/contract/*`, `backend/tests/spec/*`, `backend/tests/test_main.py`,
`backend/tests/test_turn_engine.py` have no dependency on `app.session`/`app.db` and are untouched.
New tests use the injected `FakeSupabaseClient` — no network calls, no requirement for
`SUPABASE_URL`/`SUPABASE_SERVICE_KEY` to be set in the test environment.

## Verification
1. `cd backend; uv run pytest` — new tests green, all existing ones unaffected.
2. `cd backend; uv run ruff check . && uv run ruff format --check .` — clean.
3. Manual, optional (needs real `.env` values — the Supabase project is already live per
   `docs/plans/T06-plan.md`'s build log): call `get_or_create_session`/`save_turn` with the real
   `db.get_client()` against a throwaway `session_id`, confirm a row appears via `curl` against
   `$SUPABASE_URL/rest/v1/sessions` with the service key, then leave it (no cleanup job exists yet —
   harmless test data, matches how T06's own verification left rows behind).
