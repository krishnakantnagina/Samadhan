"""S07 -- Validator + confirmation (T15). Spec: docs/specs/S07-validator.md.

Pure function: no database, no LLM, no jurisdiction resolution. Every field value the Turn Engine
(S05) proposed is checked against its spec type rule before it can be stored or shown (PROJECT.md
section 4, S01 section 2).

Either of us can change this file. If you do, update docs/specs/S07-validator.md and tell the
other.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.service_spec import FieldSpec, LocationField, ServiceSpec
from app.turn_engine import TurnResult

CONFIRM_PROMPT_HI = "कृपया जानकारी जाँचें और पुष्टि करें (हाँ/ठीक है), या सुधार बताएं।"  # PROPOSED (G-S07-1)
GPS_LOCATION_LABEL_HI = "साझा लोकेशन (GPS)"  # PROPOSED (G-S07-2)


class ValidatedAction(StrEnum):
    """S07's own vocabulary -- not S01's Action. `ready_to_submit` is never shown to the citizen;
    it tells T18 to call S10 next (S04 section 2 step 7a)."""

    ASK = "ask"
    CONFIRM = "confirm"
    OUT_OF_SCOPE = "out_of_scope"
    READY_TO_SUBMIT = "ready_to_submit"


@dataclass(frozen=True)
class SessionSnapshot:
    """Minimal session view S07 needs, decoupled from app.session.Session (D-S07-6)."""

    service_id: str | None
    collected_fields: dict[str, Any]
    awaiting_confirmation: bool
    lat: float | None
    lng: float | None


class ValidationResult(BaseModel):
    """S07 output. `reply_text` is None exactly on `ready_to_submit` -- T18 builds the real
    `submitted` reply once S10 returns a complaint_id, which this module never has."""

    service_id: str | None
    collected_fields: dict[str, Any]
    awaiting_confirmation: bool
    action: ValidatedAction
    ask_for: str | None
    reply_text: str | None
    summary: dict[str, Any] | None


# --- Per-type validation (S03 FIELDS table) --------------------------------------------------


def _validate_field(field: FieldSpec, raw_value: Any) -> Any | None:
    match field.type:
        case "enum":
            if isinstance(raw_value, str) and any(v.value == raw_value for v in field.values):
                return raw_value
            return None
        case "integer":
            if isinstance(raw_value, bool) or not isinstance(raw_value, int | str):
                return None  # bool is an int subclass -- reject before int() coerces it silently
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


def _merge_fields(
    collected: dict[str, Any], proposed: dict[str, Any], spec: ServiceSpec
) -> dict[str, Any]:
    """Unknown field names are dropped (S03 TURN RULES #4). An invalid value never erases an
    existing valid one for the same field -- it's simply not applied (D-S07-4)."""
    merged = dict(collected)
    for name, raw_value in proposed.items():
        field = spec.field(name)
        if field is None:
            continue
        validated = _validate_field(field, raw_value)
        if validated is not None:
            merged[name] = validated
    return merged


# --- Completeness (location's GPS-or-place-name duality, D-S07-3) ----------------------------


def _location_satisfied(
    field: LocationField,
    merged: dict[str, Any],
    lat: float | None,
    lng: float | None,
    session_lat: float | None,
    session_lng: float | None,
) -> bool:
    if lat is not None and lng is not None:
        return True
    if session_lat is not None and session_lng is not None:
        return True
    return field.name in merged


def _is_satisfied(
    field: FieldSpec,
    merged: dict[str, Any],
    lat: float | None,
    lng: float | None,
    session_lat: float | None,
    session_lng: float | None,
) -> bool:
    if field.type == "location":
        return _location_satisfied(field, merged, lat, lng, session_lat, session_lng)
    return field.name in merged


def _first_missing_required(
    spec: ServiceSpec,
    merged: dict[str, Any],
    lat: float | None,
    lng: float | None,
    session_lat: float | None,
    session_lng: float | None,
) -> FieldSpec | None:
    for field in spec.required_fields():
        if not _is_satisfied(field, merged, lat, lng, session_lat, session_lng):
            return field
    return None


# --- Confirmation summary (S01 section 4.2 / 4.4 note) ---------------------------------------


def _display_value(
    field: FieldSpec,
    merged: dict[str, Any],
    lat: float | None,
    lng: float | None,
    session_lat: float | None,
    session_lng: float | None,
) -> Any:
    if field.type == "location":
        if (lat is not None and lng is not None) or (
            session_lat is not None and session_lng is not None
        ):
            return GPS_LOCATION_LABEL_HI
        return merged[field.name]
    if field.type == "enum":
        return next(v.hi for v in field.values if v.value == merged[field.name])
    return merged[field.name]


def _build_summary(
    spec: ServiceSpec,
    merged: dict[str, Any],
    lat: float | None,
    lng: float | None,
    session_lat: float | None,
    session_lng: float | None,
) -> dict[str, Any]:
    return {
        f.name: _display_value(f, merged, lat, lng, session_lat, session_lng)
        for f in spec.fields
        if _is_satisfied(f, merged, lat, lng, session_lat, session_lng)
    }


# --- apply -------------------------------------------------------------------------------------


def apply(
    *,
    specs: dict[str, ServiceSpec],
    session: SessionSnapshot,
    turn_result: TurnResult,
    lat: float | None,
    lng: float | None,
) -> ValidationResult:
    if turn_result.service_id is None:
        # Not matching any loaded service this turn -- session state is untouched, so a citizen
        # mid-flow who sends one unrelated message can resume on their next message (D-S07-2).
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

    spec = specs[turn_result.service_id]  # trusted: S05 already constrains this to specs.keys()
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
