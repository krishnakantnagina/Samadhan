# S11 — Status Lookup
Implements: T19 (`backend/app/ticketing.py`, `backend/app/routes.py`) · Used by: citizen status-check
page (T22) · Depends on: S01 API contract §5, S02 DB schema (`tickets`) · Version: v1 · Status: Draft

## PURPOSE
`GET /api/v1/status/{complaint_id}` — the read-only counterpart to S10's `create_ticket`. S01 §5
already fully specifies the contract (exact four fields, two error codes); this spec only fixes the
implementation: which module owns the read, and how the route maps a lookup result to S01's errors.

## SCOPE
A new `get_status` function added to `app/ticketing.py` (S10's existing module — this is the read
half of the same `tickets` table S10 already writes to; a separate module for one query would be
unwarranted) and the `GET /status/{complaint_id}` route body in `app/routes.py`. Does not touch
`sessions`/`messages`, does not resolve jurisdiction, does not change anything S10 already does.

## BEHAVIOR
1. Route validates `complaint_id` against `api.COMPLAINT_ID_PATTERN` (`^SMD-\d{4,}$`, already in
   `schemas.py`) **before** touching the database — a malformed ID never reaches a query, matching
   the mock's own `status()` handler exactly.
2. `ticketing.get_status(complaint_id)` reads exactly `status`, `department`, `updated_at` from the
   one matching `tickets` row (`complaint_id` is `UNIQUE`, S02) — never `fields`, `original_text`,
   `lat`/`lng`, `audio_path`, or any other column (S01 §5: "Never returns transcript, audio,
   location, contact details, or collected fields").
3. No row found → `None`; the route turns that into `404 COMPLAINT_NOT_FOUND`.
4. Response: `schemas.StatusResponse(complaint_id=<the validated path param, not a DB echo>,
   status=row["status"], department=row["department"], updated_at=row["updated_at"])`.

## RULES
1. `complaint_id` format validation happens in the route, before any DB call (S01 §5's two error
   codes map cleanly to "bad format" vs. "not found" only if the format check runs first).
2. `get_status` selects only the three columns it needs — never `select("*")` — so a future column
   added to `tickets` can't accidentally leak through this endpoint without a deliberate code change.
3. No auth, matching S01 §3 ("Auth: None") — a `complaint_id` is treated as unguessable enough on its
   own for M1, same posture as `session_id`.

## ERRORS
| Situation | Result |
|---|---|
| `complaint_id` doesn't match `SMD-\d{4,}` | `400 INVALID_COMPLAINT_ID` |
| Valid format, no matching row | `404 COMPLAINT_NOT_FOUND` |
| DB error | Propagates uncaught → `500 INTERNAL_ERROR` (same posture as S06/S09/S10) |

## OUT OF SCOPE
Anything about ticket *creation* or routing (S10). Officer-side status changes (dashboard, direct DB
writes per S02 RULES §3). Caching or rate-limiting this endpoint.

## ACCEPTANCE
| Item | Covered by |
|---|---|
| A real ticket's status, department, `updated_at` returned, no other fields | §BEHAVIOR 2, 4 |
| Malformed ID → `400` before any DB call | §BEHAVIOR 1 |
| Well-formed but unknown ID → `404` | §BEHAVIOR 3 |
| Scenario 9 (PROJECT.md/S01 §10.2): officer sets "In progress" → status reflects it | Trivially true once the dashboard (T24) writes `tickets.status` directly — this endpoint just reads whatever is there |
