# Plan: T17 — Ticket + routing (`needs_review` < 0.7)

Ticket: `docs/TICKETS.md` T17 (owner Dev, depends on T15/T16 — both `[x]`, done when "`SMD-` ticket
with office"). Spec: `docs/specs/S10-ticket-routing.md`.

**Scope: T17 only.** This plan builds `backend/app/ticketing.py`. It does not wire it into
`POST /message` (T18), does not touch `app/jurisdiction.py`, `app/validator.py`, or `app/session.py`.

**Decisions this plan assumes (already resolved, see S10 DECISIONS D-S10-1…6):**
- `original_text`/`audio_path` are opaque passthrough parameters — T18 decides what to pass, this
  module just stores it (D-S10-1, G-S10-1 flagged for whoever builds T18).
- `summary_en` is built from `validated_fields` + the spec's `.en` labels, using real coordinates
  for a GPS-based location rather than a placeholder (D-S10-2).
- `needs_review` iff `confidence < min_confidence` **or** `matched_via == "fallback"`, written as
  both checks even though they're practically redundant with today's `NAME_MATCH_MIN_SCORE = 80`
  floor always clearing a `0.7` `min_confidence` (D-S10-3).
- `create_ticket` takes `session_id: uuid.UUID`, not a `Session` object (D-S10-4).
- DB errors and `JurisdictionError` propagate uncaught → `500 INTERNAL_ERROR` (D-S10-5).
- `complaint_id` is read back from the DB's generated column, never computed here (D-S10-6).

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `backend/app/ticketing.py` | Create | `TicketingError`, `create_ticket()`, and the private location-field/summary helpers |
| `backend/tests/test_ticketing.py` | Create | A minimal fake client covering both `offices` (for the internal `resolve_office` call) and `tickets` (with generated `complaint_id` simulation) |
| `docs/TICKETS.md` | Edit (last step) | Tick T17 `[x]` |

Not touched: `backend/app/main.py`, `backend/app/routes.py`, `backend/app/jurisdiction.py`,
`backend/app/validator.py`, `backend/app/session.py`, `backend/mock/*`,
`backend/tests/contract/*` — T18 wires `create_ticket` into the real route later.

## 2. Steps, in order

**S1 — `backend/app/ticketing.py`: types and location-field lookup.**
```python
class TicketingError(RuntimeError):
    """A service spec has no `type: location` field -- a spec misconfiguration (S10 ERRORS)."""


def _find_location_field(spec: ServiceSpec) -> LocationField:
    for field in spec.fields:
        if field.type == "location":
            return field
    raise TicketingError(f"service {spec.service!r} has no location field")
```

**S2 — English summary builder.**
```python
def _is_present(field, validated_fields, lat, lng) -> bool:
    if field.type == "location":
        return (lat is not None and lng is not None) or field.name in validated_fields
    return field.name in validated_fields


def _display_value_en(field, validated_fields, lat, lng) -> str:
    if field.type == "location":
        if lat is not None and lng is not None:
            return f"{lat}, {lng}"
        return validated_fields[field.name]
    if field.type == "enum":
        return next(v.en for v in field.values if v.value == validated_fields[field.name])
    return str(validated_fields[field.name])


def _build_summary_en(spec, validated_fields, lat, lng) -> str:
    parts = [
        f"{f.label.en}: {_display_value_en(f, validated_fields, lat, lng)}"
        for f in spec.fields
        if _is_present(f, validated_fields, lat, lng)
    ]
    return "; ".join(parts)
```

**S3 — `create_ticket`.**
```python
def create_ticket(
    *,
    session_id: uuid.UUID,
    spec: ServiceSpec,
    validated_fields: dict[str, Any],
    lat: float | None,
    lng: float | None,
    original_text: str,
    audio_path: str | None,
    client: Client | None = None,
) -> schemas.Ticket:
    client = client or get_client()
    location_field = _find_location_field(spec)

    match = jurisdiction.resolve_office(
        department=spec.department,
        lat=lat,
        lng=lng,
        place_name=validated_fields.get(location_field.name),
        max_match_distance_km=spec.routing.max_match_distance_km,
        client=client,
    )

    status = (
        schemas.ComplaintStatus.NEEDS_REVIEW
        if match.confidence < spec.routing.min_confidence or match.matched_via == "fallback"
        else schemas.ComplaintStatus.NEW
    )
    summary_en = _build_summary_en(spec, validated_fields, lat, lng)

    row = (
        client.table("tickets")
        .insert(
            {
                "session_id": str(session_id),
                "service_id": spec.service,
                "department": spec.department,
                "office_id": match.office.id,
                "status": status,
                "fields": validated_fields,
                "summary_en": summary_en,
                "original_text": original_text,
                "audio_path": audio_path,
                "lat": lat,
                "lng": lng,
                "routing_confidence": match.confidence,
            }
        )
        .execute()
        .data[0]
    )

    return schemas.Ticket(
        complaint_id=row["complaint_id"],
        department=spec.department,
        office=schemas.Office(name=match.office.office_name, level=match.office.level),
        status=status,
    )
```
`client` is passed through into `jurisdiction.resolve_office` explicitly (rather than letting it
call `get_client()` again) so both calls share one client instance — matters for the fake in tests,
harmless either way against the real, `lru_cache`d client.

**S4 — `backend/tests/test_ticketing.py`: fake client.**
Covers both tables `create_ticket` touches: `offices` (plain `select().eq().eq().execute()`, same
shape `jurisdiction.py` already uses) and `tickets` (`insert().execute()`, with the fake simulating
the DB's generated `complaint_id` column: `f"SMD-{next_id:04d}"`, mirroring T03's `lpad` behavior
closely enough for these tests). Self-contained in this file, not shared with `test_jurisdiction.py`
or `test_session.py`'s fakes (same one-fake-per-ticket pattern used throughout).

**S5 — Tests.**
- `test_gps_match_creates_new_status_ticket` — a ward centroid close to the given GPS →
  `status="new"`, `office.level="ward"`, `complaint_id` matches `SMD-\d{4,}`.
- `test_unknown_location_creates_needs_review_district_ticket` — no ward matches an unrelated
  place name → `status="needs_review"`, `office.level="district"`.
- `test_name_match_below_custom_min_confidence_is_still_needs_review` — a spec with
  `routing.min_confidence=0.95` (higher than any name match's confidence ceiling, since
  `NAME_MATCH_MIN_SCORE=80` caps it at `0.8`–`1.0` in practice) and a valid alias match → confirms
  the literal `confidence < min_confidence` check works on its own, not just the redundant
  `matched_via == "fallback"` half (D-S10-3's whole reason for writing both checks).
- `test_summary_en_includes_english_labels_and_values` — an enum + integer field → `summary_en`
  contains `"Issue: No water"` and `"Days affected: 3"` style substrings (label.en + value.en).
- `test_summary_en_uses_coordinates_for_gps_location` — GPS given → `summary_en` contains the raw
  `lat, lng` numbers, not a placeholder string.
- `test_ticket_fields_column_matches_validated_fields_exactly` — the inserted row's `fields` column
  equals the `validated_fields` dict passed in, unmodified.
- `test_spec_without_location_field_raises` — a hand-built spec with no `type: location` field →
  `TicketingError`.

## 3. Acceptance coverage

| S10 acceptance item | Covered by |
|---|---|
| Scenario 7: GPS in a pilot ward → `submitted`, `office.level="ward"` | S5 `test_gps_match_creates_new_status_ticket` |
| Scenario 8: unknown location → `office.level="district"`, `status="needs_review"` | S5 `test_unknown_location_creates_needs_review_district_ticket` |
| `complaint_id` matches `SMD-\d{4,}` | S5 `test_gps_match_creates_new_status_ticket` (pattern-asserted) |
| `routing_confidence`/`office_id` stored from S09's resolution, not re-derived | S5 `test_ticket_fields_column_matches_validated_fields_exactly` + the fake's insert payload assertions |

## 4. New libraries
None — reuses `app.jurisdiction`, `app.schemas`, `app.service_spec`, `app.db` as they already are.

## 5. How existing tests stay unaffected
`backend/app/ticketing.py` is new and self-contained; nothing in `backend/mock/*`,
`backend/tests/contract/*`, `backend/tests/spec/*`, or the T12/T14/T15/T16 test files imports it.

## Verification
1. `cd backend; uv run pytest` — new tests green, all existing ones unaffected.
2. `cd backend; uv run ruff check . && uv run ruff format --check .` — clean.
3. Manual, optional (needs real `.env`, Supabase project already live): call `create_ticket(...)`
   with a real `session_id` (create one via `get_or_create_session` first, to satisfy the FK) and
   confirm a real row lands in `tickets` with a genuine `SMD-####` `complaint_id`.

## Not doing in this turn
Not implementing `ticketing.py` itself until this plan is reviewed — same two-step pattern as
T12/T14/T15/T16.
