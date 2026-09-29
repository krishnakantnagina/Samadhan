"""S07 -- Validator + confirmation (T15). Spec: docs/specs/S07-validator.md.

Pure function: no database, no LLM, no jurisdiction resolution. Every field value the Turn Engine
(S05) proposed is checked against its spec type rule before it can be stored or shown (PROJECT.md
section 4, S01 section 2).

Either of us can change this file. If you do, update docs/specs/S07-validator.md and tell the
other.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.info_reply import OUT_OF_CONTEXT_REPLY_HI, URGENT_LINE_HI, build_info_reply
from app.service_spec import FieldSpec, LocationField, ServiceSpec
from app.turn_engine import GENERAL_SERVICE, TurnResult

CONFIRM_PROMPT_HI = "कृपया जानकारी जाँचें और पुष्टि करें (हाँ/ठीक है), या सुधार बताएं।"  # PROPOSED (G-S07-1)
GPS_LOCATION_LABEL_HI = "साझा लोकेशन (GPS)"  # PROPOSED (G-S07-2)
CONFIDENT = 0.8  # S28 4.3: at or above, route without asking
RECONFIRM_MIN = 0.5  # S28 4.3: from here up to CONFIDENT, ask 'are you reporting X?'


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


# S23 section 5: a bare yes/no answer to "are you at the place of the problem?" is not a place. Kept in
# sync by hand with the word lists in frontend/app.js + widget.js (D-S23-4).
YES_NO_WORDS = frozenset(
    {
        # YES (frontend LOCATION_YES)
        "हाँ", "हां", "हा", "जी", "जी हाँ", "जी हां", "yes", "y", "ok", "okay", "ठीक है",
        "हाँ मैं यहीं हूँ", "हां मैं यहीं हूं", "यहीं हूँ", "यहीं हूं",
        # NO (frontend LOCATION_NO)
        "नहीं", "नही", "ना", "जी नहीं", "no", "n", "नहीं मैं यहाँ नहीं हूँ", "मैं यहाँ नहीं हूँ",
        "घर पर हूँ", "मैं घर पर हूँ",
    }
)  # fmt: skip


def _is_yes_no_answer(text: str) -> bool:
    cleaned = " ".join(text.lower().replace(",", " ").split()).strip(".।!?")
    return cleaned in YES_NO_WORDS


ACK_MIN_LENGTH = 3
ACK_MAX_LENGTH = 120
# S25 D-S25-5: promise / action words. The bot must not claim anyone is acting on the complaint.
ACK_BLOCKED_WORDS = (
    "जल्द", "जाँच", "जांच", "देख रहे", "कार्रवाई", "कार्यवाही", "ठीक कर", "समाधान कर", "भेज",
    "जायेगा", "जाएगा", "करेंगे", "करूँगा", "करूंगा",
)  # fmt: skip


def _clean_ack(ack: Any) -> str | None:
    """S25 section 2: the LLM's acknowledgement is decoration, never trusted. Anything odd is dropped
    and the reply falls back to the spec's plain question."""
    if not isinstance(ack, str):
        return None
    text = " ".join(ack.split())
    if not ACK_MIN_LENGTH <= len(text) <= ACK_MAX_LENGTH:
        return None
    lowered = text.lower()
    if "?" in text or "\uff1f" in text or "http" in lowered or "www" in lowered:
        return None
    if re.search(r"\d{4,}", text):
        return None
    if any(word in text for word in ACK_BLOCKED_WORDS):
        return None
    return text


# S27: generic place nouns and filler words. A location made ONLY of these names no place ("हमाए गाँव",
# "our village", "hand pump"); any other word (a real name, a number) makes it acceptable. Backend only.
GENERIC_PLACE_WORDS = frozenset(
    {
        # Devanagari nouns
        "गाँव", "गांव", "गाव", "ग्राम", "मोहल्ला", "मोहल्ले", "मुहल्ला", "घर", "घरों", "घरन", "मकान",
        "हैंडपंप", "हैण्डपंप", "हैंड", "पंप", "नल", "टंकी", "टंकि", "पानी", "कॉलोनी", "कालोनी", "इलाका",
        "इलाके", "क्षेत्र", "बस्ती", "गली", "सड़क", "रोड", "वार्ड", "नंबर", "शहर", "कस्बा",
        # Devanagari fillers
        "हमाए", "हमारे", "हमारा", "हमारी", "हमाई", "हमारो", "मेरे", "मेरा", "मेरी", "अपने", "अपना",
        "का", "के", "की", "को", "में", "मे", "पर", "पास", "यहाँ", "यहां", "वहाँ", "वहां", "यहीं", "इस",
        "उस", "आसपास", "और", "से", "एक",
        # Latin nouns
        "gaon", "gaanv", "gav", "gram", "village", "mohalla", "mohalle", "muhalla", "ghar", "house",
        "home", "handpump", "hand", "pump", "nal", "tap", "tank", "tanki", "colony", "area", "ilaka",
        "ilake", "kshetra", "basti", "gali", "street", "road", "ward", "number", "no", "sadak",
        "shahar", "city", "town", "paani", "water",
        # Latin fillers
        "hamare", "hamaare", "hamara", "hamari", "hamaye", "mere", "mera", "meri", "apne", "our", "my",
        "the", "of", "in", "at", "near", "nearby", "here", "there", "yaha", "yahan", "wahan", "ka",
        "ke", "ki", "me", "mein", "par", "pas", "a", "an",
    }
)  # fmt: skip


def _is_generic_place(text: str) -> bool:
    tokens = re.sub(r"[.,।!?;:()\-\"']", " ", text.lower()).split()
    return bool(tokens) and all(token in GENERIC_PLACE_WORDS for token in tokens)


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
            if _is_yes_no_answer(trimmed) or _is_generic_place(trimmed):
                return None  # S23 section 5, S27
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


def _with_ack(ack: Any, question: str) -> str:
    cleaned = _clean_ack(ack)
    if not cleaned:
        return question
    if cleaned[-1] not in ".।!":
        cleaned += "।"  # never let the ack run into the question
    return f"{cleaned} {question}"


def _urgent(turn_result: TurnResult, text: str) -> str:
    """S28 Q4: immediate danger gets a fixed neutral line first (no numbers: none are verified)."""
    return f"{URGENT_LINE_HI} {text}" if turn_result.urgent else text


def _passthrough(
    session: SessionSnapshot, turn_result: TurnResult, reply: str
) -> "ValidationResult":
    """A reply that leaves the session exactly as it was (S28 4.6): a side question mid-complaint
    never resets the complaint, and no ticket or triage entry is created."""
    return ValidationResult(
        service_id=session.service_id,
        collected_fields=session.collected_fields,
        awaiting_confirmation=session.awaiting_confirmation,
        action=ValidatedAction.OUT_OF_SCOPE,
        ask_for=None,
        reply_text=_urgent(turn_result, reply),
        summary=None,
    )


def _carry_over(spec: ServiceSpec, collected: dict[str, Any]) -> dict[str, Any]:
    """Fields collected under another service that are still valid under `spec` (e.g. the location).
    Anything invalid for `spec` (an enum value from another department) is dropped, never kept."""
    kept: dict[str, Any] = {}
    for name, value in collected.items():
        field = spec.field(name)
        if field is not None and _validate_field(field, value) is not None:
            kept[name] = value
    return kept


def _common_fields(
    specs: list[ServiceSpec], proposed: dict[str, Any], collected: dict[str, Any]
) -> dict[str, Any]:
    """Unsure between departments: keep only what is valid under EVERY candidate (in practice the
    location), so the citizen is not asked for it again after they pick one."""
    merged = dict(collected)
    for name, value in proposed.items():
        checks = [(sp.field(name), sp) for sp in specs]
        if all(f is not None and _validate_field(f, value) is not None for f, _ in checks):
            merged[name] = _validate_field(checks[0][0], value)
    return merged


def _list_labels(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " या " + labels[-1]


def apply(
    *,
    specs: dict[str, ServiceSpec],
    session: SessionSnapshot,
    turn_result: TurnResult,
    lat: float | None,
    lng: float | None,
) -> ValidationResult:
    # --- 1. What kind of message is it? (S28 4.3a). Anything that already changed the complaint
    # (a confirmation or a field) is a complaint turn whatever the label says: a short "haan" must
    # never be treated as chit-chat.
    intent = turn_result.intent
    if turn_result.confirmed or turn_result.fields:
        intent = "complaint"
    if intent == "information":
        return _passthrough(session, turn_result, build_info_reply(turn_result.info_url))
    if intent == "out_of_context":
        return _passthrough(session, turn_result, OUT_OF_CONTEXT_REPLY_HI)

    # --- 2. Which department? (S28 4.3). The active service is sticky: a follow-up in the middle of
    # a complaint never re-routes it, and only an explicit different service switches it.
    active = session.service_id if session.service_id in specs else None
    service_id = turn_result.service_id
    candidates = [c for c in turn_result.candidates if c in specs and c != GENERAL_SERVICE]

    if (
        service_id is not None
        and service_id != active
        and service_id != GENERAL_SERVICE
        and turn_result.confidence is not None
        and turn_result.confidence < CONFIDENT
    ):
        if turn_result.confidence >= RECONFIRM_MIN:
            candidates = [service_id]  # fairly sure: reconfirm just this one
        else:
            candidates = candidates or [service_id]  # unsure: at least this one is a candidate
        service_id = None

    if service_id is None:
        if len(candidates) >= 2:
            cand_specs = [specs[c] for c in candidates]
            question = f"क्या यह {_list_labels([sp.label.hi for sp in cand_specs])} है?"
            return ValidationResult(
                service_id=None,
                collected_fields=_common_fields(
                    cand_specs, turn_result.fields, session.collected_fields
                ),
                awaiting_confirmation=False,
                action=ValidatedAction.ASK,
                ask_for="service",
                reply_text=_urgent(turn_result, question),
                summary=None,
            )
        if len(candidates) == 1:
            spec = specs[candidates[0]]
            base = (
                _carry_over(spec, session.collected_fields)
                if active != spec.service
                else session.collected_fields
            )
            return ValidationResult(
                service_id=spec.service,  # tentative: the next turn's yes/no settles it
                collected_fields=_merge_fields(base, turn_result.fields, spec),
                awaiting_confirmation=False,
                action=ValidatedAction.ASK,
                ask_for="service",
                reply_text=_urgent(turn_result, f"क्या आप {spec.label.hi} बता रहे हैं?"),
                summary=None,
            )
        if GENERAL_SERVICE in specs:
            # Multi-department mode (S28). No new routing information mid-complaint: stay in it;
            # otherwise a real complaint that fits no department goes to triage (D-S28-4).
            service_id = active if active is not None else GENERAL_SERVICE
        else:
            # Single-service deployment (no general spec): the pre-S28 behaviour, unchanged.
            fallback_id = next(iter(specs))
            return ValidationResult(
                service_id=session.service_id,
                collected_fields=session.collected_fields,
                awaiting_confirmation=session.awaiting_confirmation,
                action=ValidatedAction.OUT_OF_SCOPE,
                ask_for=None,
                reply_text=specs[fallback_id].out_of_scope.reply.hi,
                summary=None,
            )

    spec = specs[service_id]  # trusted: S05 constrains service ids to specs.keys()
    switched = active is not None and service_id != active
    base = _carry_over(spec, session.collected_fields) if switched else session.collected_fields
    merged = _merge_fields(base, turn_result.fields, spec)
    confirmed = turn_result.confirmed and not switched  # a switch is never a confirmation
    missing = _first_missing_required(spec, merged, lat, lng, session.lat, session.lng)

    if missing is not None:
        return ValidationResult(
            service_id=spec.service,
            collected_fields=merged,
            awaiting_confirmation=False,
            action=ValidatedAction.ASK,
            ask_for=missing.ask_for if missing.type == "location" else missing.name,
            reply_text=_urgent(turn_result, _with_ack(turn_result.ack, missing.question.hi)),
            summary=None,
        )

    summary = _build_summary(spec, merged, lat, lng, session.lat, session.lng)

    if confirmed:
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
        reply_text=_urgent(turn_result, CONFIRM_PROMPT_HI),
        summary=summary,
    )
