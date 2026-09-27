# Plan: T19 — Real `GET /status/{complaint_id}`

Ticket: `docs/TICKETS.md` T19 (owner Dev, depends on T17 — `[x]`, done when "Correct status").
Spec: `docs/specs/S11-status-lookup.md` (new — S01's own header already referenced an "S11 Status
lookup" spec that was never written).

**Scope: T19 only.** Adds `get_status` to the existing `backend/app/ticketing.py` (S10's module —
this is the read half of the same table) and the `GET /status/{complaint_id}` route body.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `backend/app/ticketing.py` | Edit | Add `get_status(complaint_id, *, client=None) -> dict \| None` |
| `backend/app/routes.py` | Edit | Add the `GET /status/{complaint_id}` route |
| `backend/tests/test_ticketing.py` | Edit | Tests for `get_status` (found / not found) |
| `backend/tests/test_routes.py` | Edit | Tests for the route's 200/400/404 mapping |
| `docs/TICKETS.md` | Edit (last step) | Tick T19 `[x]` |

## 2. Steps, in order

**S1 — `app/ticketing.py`: `get_status`.**
```python
def get_status(complaint_id: str, *, client: Client | None = None) -> dict[str, Any] | None:
    client = client or get_client()
    rows = (
        client.table("tickets")
        .select("status,department,updated_at")
        .eq("complaint_id", complaint_id)
        .execute()
    ).data
    return rows[0] if rows else None
```

**S2 — `app/routes.py`: the route.**
```python
import re

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
```
Mirrors the mock's own `status()` handler almost exactly (S11 BEHAVIOR §1).

**S3 — `test_ticketing.py` additions.**
- `test_get_status_found` — seed a `tickets` row in the existing `FakeClient`, assert the three
  fields come back, nothing else.
- `test_get_status_not_found` — no matching row → `None`.

**S4 — `test_routes.py` additions.**
- `test_status_returns_200_for_a_real_ticket` — monkeypatch `routes.ticketing.get_status` to return
  a canned dict → `200` with the right body.
- `test_status_malformed_id_is_400` — `GET /api/v1/status/SMD-ABC` → `400`, and
  `ticketing.get_status` is never called (monkeypatched to raise if it is).
- `test_status_unknown_id_is_404` — `get_status` returns `None` → `404`.

**S5 — Run the suite and lint.** `cd backend; uv run pytest` and
`uv run ruff check . && uv run ruff format --check .`.

**S6 — Tick it off.** `docs/TICKETS.md`: T19 `[x]`.

## 3. Acceptance coverage

| S11 acceptance item | Covered by |
|---|---|
| Real ticket → status/department/updated_at only | S3 `test_get_status_found` |
| Malformed ID → `400` before any DB call | S4 `test_status_malformed_id_is_400` |
| Unknown ID → `404` | S4 `test_status_unknown_id_is_404` |

## 4. New libraries
None.

## Verification
1. `cd backend; uv run pytest` — new tests green, all existing ones unaffected.
2. `cd backend; uv run ruff check . && uv run ruff format --check .` — clean.
3. Manual, optional (real `.env`, live Supabase): `GET /api/v1/status/SMD-0001` against a real ticket
   created during T17/T18's live checks, confirm it returns the right status.

## Not doing in this turn
Not implementing until this plan is reviewed — same pattern as T12/T14–T18.
