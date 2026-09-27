# Plan: T15 — Validator + confirmation

Ticket: `docs/TICKETS.md` T15 (owner Dev, depends on T11/T12/T14 — all already `[x]`, done when
"No invalid tickets"). Spec: `docs/specs/S07-validator.md`.

**Scope: T15 only.** This plan builds `backend/app/validator.py`. It does **not** wire it into
`POST /message` (T18), does not touch jurisdiction resolution or ticket creation (S09/S10, T16/T17),
and does not touch `app/session.py`, `app/turn_engine.py`, or `app/service_spec.py`.

**Decisions this plan assumes (already resolved, see S07 DECISIONS D-S07-1…6):**
- All generated reply text is `.hi` only (D-S07-1).
- An out-of-scope turn never mutates `service_id`/`collected_fields`/`awaiting_confirmation` — only
  this turn's reply is affected (D-S07-2).
- GPS, once given, keeps `location` satisfied for the rest of the session, not just the turn it
  arrived on (D-S07-3).
- An invalid proposed field value never erases an existing valid one for the same field (D-S07-4).
- A new `ValidatedAction` enum, not S01's `Action` — `ready_to_submit` is internal-only (D-S07-5).
- `SessionSnapshot` is `validator.py`'s own minimal dataclass, decoupled from `app.session.Session`
  (D-S07-6) — same pattern `turn_engine.SessionState` already uses.

**New implementation decisions this plan makes** (S07 stays at the behavior level, not Python
mechanics):
- Per-type validation (`_validate_field`) uses `match field.type` structural pattern matching over
  the four `FieldSpec` variants from `app.service_spec` — one `case` per type, mirroring how
  `turn_engine._field_vocabulary` already branches with `isinstance` checks on the same types.
- Integer coercion explicitly rejects `bool` before calling `int(raw_value)` — `bool` is an `int`
  subclass in Python, so `isinstance(raw_value, bool)` must be checked first or a JSON `true`/`false`
  would silently coerce to `1`/`0`.
- `CONFIRM_PROMPT_HI` and `GPS_LOCATION_LABEL_HI` are module-level string constants, each commented
  `# PROPOSED (G-S07-1/G-S07-2)` — exactly how `specs/water_supply.yaml` already flags its own
  unconfirmed values, so the pattern is visually familiar to whoever reviews this file next.
- `apply()` is a single pure function with no injectable seam needed (unlike T12's `providers` or
  T14's `client`) — there's no I/O to fake here, so tests just call it directly with hand-built
  `ServiceSpec`/`SessionSnapshot`/`TurnResult` values.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `backend/app/validator.py` | Create | `SessionSnapshot`, `ValidatedAction`, `ValidationResult`, `apply()`, and the private per-type/completeness/summary helpers |
| `backend/tests/test_validator.py` | Create | Full behavior coverage against hand-built specs, no fakes/mocks needed |
| `docs/TICKETS.md` | Edit (last step) | Tick T15 `[x]` |

Not touched: `backend/app/main.py`, `backend/app/routes.py`, `backend/app/session.py`,
`backend/app/turn_engine.py`, `backend/app/service_spec.py`, `backend/mock/*`,
`backend/tests/contract/*` — T18 wires `validator.py` into the real route later.

## 2. Steps, in order

**S1 — `backend/app/validator.py`: types.**
```python
class ValidatedAction(StrEnum):
    ASK = "ask"
    CONFIRM = "confirm"
    OUT_OF_SCOPE = "out_of_scope"
    READY_TO_SUBMIT = "ready_to_submit"


@dataclass(frozen=True)
class SessionSnapshot:
    service_id: str | None
    collected_fields: dict[str, Any]
    awaiting_confirmation: bool
    lat: float | None
    lng: float | None


class ValidationResult(BaseModel):
    service_id: str | None
    collected_fields: dict[str, Any]
    awaiting_confirmation: bool
    action: ValidatedAction
    ask_for: str | None
    reply_text: str | None
    summary: dict[str, Any] | None


CONFIRM_PROMPT_HI = "कृपया जानकारी जाँचें और पुष्टि करें (हाँ/ठीक है), या सुधार बताएं।"  # PROPOSED (G-S07-1)
GPS_LOCATION_LABEL_HI = "साझा लोकेशन (GPS)"  # PROPOSED (G-S07-2)
```

**S2 — Per-type validation.**
```python
def _validate_field(field: FieldSpec, raw_value: Any) -> Any | None:
    match field.type:
        case "enum":
            if isinstance(raw_value, str) and any(v.value == raw_value for v in field.values):
                return raw_value
            return None
        case "integer":
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, str)):
                return None
            try:
                value = int(raw_value)
            except ValueError:
                return None
            return value if field.min <= value <= field.max else None
        case "string":
            if not isinstance(raw_value, str):
                return None
            trimmed = raw_value.strip()
            return trimmed if trimmed and len(trimmed) <= field.max_length else None
        case "location":
            if not isinstance(raw_value, str):
                return None
            trimmed = raw_value.strip()
            bounds = field.accepts.place_name
            return trimmed if bounds.min_length <= len(trimmed) <= bounds.max_length else None
```

**S3 — Merge.**
```python
def _merge_fields(
    collected: dict[str, Any], proposed: dict[str, Any], spec: ServiceSpec
) -> dict[str, Any]:
    merged = dict(collected)
    for name, raw_value in proposed.items():
        field = spec.field(name)
        if field is None:
            continue  # unknown field name (S03 TURN RULES #4)
        validated = _validate_field(field, raw_value)
        if validated is not None:
            merged[name] = validated
        # else: drop silently, existing value (if any) stays untouched (D-S07-4)
    return merged
```

**S4 — Completeness.**
```python
def _location_satisfied(
    field: LocationField, merged: dict[str, Any], lat, lng, session_lat, session_lng
) -> bool:
    if lat is not None and lng is not None:
        return True
    if session_lat is not None and session_lng is not None:
        return True
    return field.name in merged


def _is_satisfied(field, merged, lat, lng, session_lat, session_lng) -> bool:
    if field.type == "location":
        return _location_satisfied(field, merged, lat, lng, session_lat, session_lng)
    return field.name in merged


def _first_missing_required(spec, merged, lat, lng, session_lat, session_lng):
    for field in spec.required_fields():
        if not _is_satisfied(field, merged, lat, lng, session_lat, session_lng):
            return field
    return None
```

**S5 — Summary.**
```python
def _display_value(field, merged, lat, lng, session_lat, session_lng) -> Any:
    if field.type == "location":
        if (lat is not None and lng is not None) or (
            session_lat is not None and session_lng is not None
        ):
            return GPS_LOCATION_LABEL_HI
        return merged[field.name]
    if field.type == "enum":
        return next(v.hi for v in field.values if v.value == merged[field.name])
    return merged[field.name]


def _build_summary(spec, merged, lat, lng, session_lat, session_lng) -> dict[str, Any]:
    return {
        f.name: _display_value(f, merged, lat, lng, session_lat, session_lng)
        for f in spec.fields
        if _is_satisfied(f, merged, lat, lng, session_lat, session_lng)
    }
```

**S6 — `apply()`.**
```python
def apply(
    *,
    specs: dict[str, ServiceSpec],
    session: SessionSnapshot,
    turn_result: TurnResult,
    lat: float | None,
    lng: float | None,
) -> ValidationResult:
    if turn_result.service_id is None:
        fallback_id = session.service_id or next(iter(specs))
        return ValidationResult(
            service_id=session.service_id,
            collected_fields=session.collected_fields,
            awaiting_confirmation=session.awaiting_confirmation,
            action=ValidatedAction.OUT_OF_SCOPE,
            ask_for=None,
            reply_text=specs[fallback_id].out_of_scope.reply.hi,
            summary=None,
        )

    spec = specs[turn_result.service_id]  # trusted per S05 structural validation (RULES 1)
    merged = _merge_fields(session.collected_fields, turn_result.fields, spec)
    missing = _first_missing_required(spec, merged, lat, lng, session.lat, session.lng)

    if missing is not None:
        return ValidationResult(
            service_id=spec.service,
            collected_fields=merged,
            awaiting_confirmation=False,
            action=ValidatedAction.ASK,
            ask_for=missing.ask_for if missing.type == "location" else missing.name,
            reply_text=missing.question.hi,
            summary=None,
        )

    summary = _build_summary(spec, merged, lat, lng, session.lat, session.lng)
    if turn_result.confirmed:
        return ValidationResult(
            service_id=spec.service,
            collected_fields=merged,
            awaiting_confirmation=False,
            action=ValidatedAction.READY_TO_SUBMIT,
            ask_for=None,
            reply_text=None,
            summary=summary,
        )

    return ValidationResult(
        service_id=spec.service,
        collected_fields=merged,
        awaiting_confirmation=True,
        action=ValidatedAction.CONFIRM,
        ask_for=None,
        reply_text=CONFIRM_PROMPT_HI,
        summary=summary,
    )
```

**S7 — `backend/tests/test_validator.py`.**
Build a minimal two-field `ServiceSpec` once at module scope (one required `enum` field
`issue_type`, one required `location` field), reusing `ServiceSpec.model_validate(...)` the same
way `test_turn_engine.py`'s `make_spec()` already does — no YAML file needed.
- `test_missing_required_field_asks` — no fields collected → `action=ask`,
  `ask_for="issue_type"` (spec order), `reply_text` = its `question.hi`.
- `test_location_missing_asks_for_location` — `issue_type` given, no location/GPS →
  `action=ask`, `ask_for="location"`.
- `test_all_fields_in_one_turn_goes_straight_to_confirm` — both fields given in one
  `turn_result.fields`, `confirmed=False` → `action=confirm`, `summary` has both keys.
- `test_gps_satisfies_location_without_a_place_name` — `lat`/`lng` passed, no `location` in
  `merged` → still reaches `confirm`/`ready_to_submit`, `summary["location"] ==
  GPS_LOCATION_LABEL_HI`.
- `test_gps_from_a_previous_turn_still_satisfies_location` — `session.lat`/`session.lng` set,
  this turn's `lat`/`lng` both `None` → still satisfied.
- `test_correction_at_confirmation_stays_confirm_not_ready` — `awaiting_confirmation=True`,
  `turn_result.confirmed=False`, a changed field value → `action=confirm` again, `summary`
  reflects the new value, not `ready_to_submit`.
- `test_confirmed_turn_reaches_ready_to_submit` — `awaiting_confirmation=True`,
  `turn_result.confirmed=True`, all required fields already satisfied → `action=ready_to_submit`,
  `reply_text is None`.
- `test_invalid_enum_value_is_dropped_field_stays_missing` — `turn_result.fields =
  {"issue_type": "electricity"}` (not in the spec's allowed values) → `action=ask`,
  `ask_for="issue_type"` still (never stored).
- `test_invalid_value_does_not_erase_existing_valid_one` — `session.collected_fields =
  {"issue_type": "no_supply"}`, `turn_result.fields = {"issue_type": "not_a_real_value"}` →
  `merged["issue_type"]` still `"no_supply"`.
- `test_out_of_scope_preserves_session_state` — `session.service_id="water_supply"`,
  non-empty `collected_fields`, `awaiting_confirmation=True`; `turn_result.service_id=None` →
  `action=out_of_scope`, and `result.service_id`/`collected_fields`/`awaiting_confirmation` all
  equal `session`'s, unchanged.
- `test_out_of_scope_before_any_service_identified` — `session.service_id=None`,
  `turn_result.service_id=None` → `action=out_of_scope`, `reply_text` is the only loaded spec's
  `out_of_scope.reply.hi`.
- `test_integer_field_rejects_bool` — `turn_result.fields = {"duration_days": True}` on a spec
  with an optional integer field → dropped, not stored as `1`.
- `test_enum_summary_shows_localized_label_not_raw_value` — `summary["issue_type"]` is the `.hi`
  label, not the raw `snake_case` value.

## 3. Acceptance coverage

| S07 acceptance item | Covered by |
|---|---|
| Scenario 1/2: only `location` missing → `ask` | S7 `test_location_missing_asks_for_location` |
| Scenario 3: all fields in one message → `confirm` directly | S7 `test_all_fields_in_one_turn_goes_straight_to_confirm` |
| Scenario 4: correction at confirmation → `confirm` again, not `ready_to_submit` | S7 `test_correction_at_confirmation_stays_confirm_not_ready` |
| Scenario 6: unrelated message → `out_of_scope`, nothing invented | S7 `test_out_of_scope_before_any_service_identified` |
| Scenario 7 (GPS): GPS satisfies `location` without a place name | S7 `test_gps_satisfies_location_without_a_place_name` |
| Invalid value dropped, not `action=error`, doesn't erase a prior valid value | S7 `test_invalid_enum_value_is_dropped_field_stays_missing` + `test_invalid_value_does_not_erase_existing_valid_one` |
| `confirmed` can't skip straight to `ready_to_submit` without a real confirm step | S7 `test_confirmed_turn_reaches_ready_to_submit` relies on S05's own `confirmed`-forcing (D-S05-3), not re-tested here |

## 4. New libraries
None — `pydantic` (for `ValidationResult`) and `dataclasses`/`enum` (stdlib) are already used
throughout `backend/app`.

## 5. How existing tests stay unaffected
`backend/app/validator.py` is a new, self-contained module. Nothing in `backend/mock/*`,
`backend/tests/contract/*`, `backend/tests/spec/*`, `test_main.py`, `test_turn_engine.py`,
`test_session.py`, or `test_db.py` imports it.

## Verification
1. `cd backend; uv run pytest` — new tests green, all existing ones unaffected.
2. `cd backend; uv run ruff check . && uv run ruff format --check .` — clean.
3. No live/manual verification needed here (unlike T12/T14) — `apply()` has no external
   dependency to smoke-test against; the unit tests in S7 are the full verification surface.

## Not doing in this turn
Not implementing `validator.py` itself — only writing this plan document to
`docs/plans/T15-plan.md`. Implementation follows once approved, as a separate step (same as
T12/T14).
