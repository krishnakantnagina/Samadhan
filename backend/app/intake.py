"""S30 -- Intake v2: the Lead's decided conversation flow (2026-10-01). OFF unless INTAKE_V2 is on and TYPESAFE_API_KEY is set.

Flow (code owns it; Jev only decides, the LLM only extracts text, see app/jev.py and app/turn_engine.py):
  1. Jev picks the department from the registry (specs/registry/departments.yaml).
  2. Confident (>= route threshold): carry on with that department. A department with a spec (water, electricity, roads, sanitation) uses its spec; any other
     department goes to Human Evaluation with the suggested department recorded, so a person can assign it (Human Evaluation in the CM dashboard).
  3. Not confident: ask ONE yes/no question about the department Jev suggests most. A yes confirms it; a no (or anything else) goes to Human Evaluation as
     "department_unconfirmed" for a person. Never a second question about the department.
  4. When every required detail is in: if the place is not clear (no GPS and no office match) ask district / tehsil / nearest town, once; then ask how
     long the problem has lasted, once. "Don't know" is accepted.
  5. Jev unreachable, flag off, no key, or no `general` spec: everything behaves exactly as before (the existing LLM path).
State travels in `collected_fields["_intake"]` (kept by the validator, copied into tickets.fields, hidden from the LLM prompt).
"""

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app import jev, jurisdiction, location_details, triage, validator
from app.service_spec import ServiceSpec
from app.turn_engine import HUMAN_EVALUATION_SERVICE, TurnResult

logger = logging.getLogger(__name__)

META_KEY = "_intake"
REGISTRY_PATH = Path(__file__).resolve().parents[2] / "specs" / "registry" / "departments.yaml"
ASK_PROBLEM_HI = "क्या आपकी समस्या {dept} से जुड़ी है? (हाँ / नहीं)"
ASK_LOCATION_DETAIL_HI = "आपका जिला और तहसील (या सबसे पास का कस्बा या गाँव) कौन सा है?"
ASK_DURATION_HI = "यह समस्या कितने दिनों से है? अगर पता न हो तो 'पता नहीं' कहें।"
REASON_NOT_LIVE = "department_not_live"  # Jev is sure, but no spec/offices exist for that department yet
REASON_UNCONFIRMED = "department_unconfirmed"  # Jev unsure and the citizen did not confirm the one question
AGREE_MIN = 0.5


@dataclass(frozen=True)
class Registry:
    departments: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]]
    live_specs: dict[str, str]
    route: float
    reconfirm: float


@lru_cache
def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    deps = raw["departments"]
    return Registry(deps, {d["id"]: d for d in deps}, dict(raw["live_specs"]), float(raw["thresholds"]["route"]), float(raw["thresholds"]["reconfirm"]))


def enabled() -> bool:
    return os.environ.get("INTAKE_V2", "").strip().lower() in ("1", "true", "yes", "on")


_decider: jev.Decider | None = None


def default_decider() -> jev.Decider | None:
    global _decider
    if _decider is None:
        _decider = jev.from_env()
    return _decider


@dataclass
class Pre:
    """What happens before the validator. `meta` None = intake did nothing this turn (existing behaviour)."""

    turn_result: TurnResult
    meta: dict[str, Any] | None = None
    ask: str | None = None  # a question to send now instead of running the validator
    ask_for: str = "service"


def get_meta(collected: dict[str, Any]) -> dict[str, Any]:
    return dict(collected.get(META_KEY) or {})


def _state(text: str, recent: list[Any]) -> dict[str, Any]:
    turns = [{"role": getattr(m, "role", "citizen"), "text": getattr(m, "text", "")} for m in (recent or [])[-4:]]
    return {"previous_turns": turns, "citizen_message": text}


def _suggest(dept: dict[str, Any]) -> dict[str, str]:
    return {"id": dept["id"], "name_en": dept["name_en"], "name_hi": dept["name_hi"]}


def _route_to(turn: TurnResult, dept: dict[str, Any], specs: dict[str, ServiceSpec], reg: Registry, meta: dict[str, Any], reason: str | None) -> Pre:
    """Continue the normal pipeline with this department chosen (sure: confidence 1.0, nothing left to reconfirm)."""
    spec_id = reg.live_specs.get(dept["id"])
    if spec_id in specs and reason != REASON_UNCONFIRMED:
        service = spec_id
        meta["reason"] = reason
    else:
        service = HUMAN_EVALUATION_SERVICE
        meta["reason"] = reason if reason == REASON_UNCONFIRMED else REASON_NOT_LIVE
    meta["suggested_department"] = _suggest(dept)
    meta["pending_dept"] = None
    return Pre(turn.model_copy(update={"service_id": service, "confidence": 1.0, "candidates": [], "intent": "complaint"}), meta)


def prestep(*, row: Any, specs: dict[str, ServiceSpec], text: str, recent: list[Any], turn_result: TurnResult,
            decider: jev.Decider | None = None, registry: Registry | None = None) -> Pre:
    if not enabled() or HUMAN_EVALUATION_SERVICE not in specs:
        return Pre(turn_result)
    decider = decider or default_decider()
    if decider is None:
        return Pre(turn_result)
    reg = registry or load_registry()
    meta = get_meta(row.collected_fields)
    try:
        if meta.get("awaiting_location_detail"):  # the answer to "which district / tehsil?": keep it for the officer, then carry on as usual
            meta["location_details"] = location_details.parse(text).as_meta()  # structured: district, tehsil, nearest place; or unknown ("I don't know" is fine)
            meta["awaiting_location_detail"] = False
            active = specs.get(row.service_id)  # the LLM may read the answer as a NEW place: never let it replace the village the citizen named
            location_names = {f.name for f in active.fields if f.type == "location"} if active else set()
            turn_result = turn_result.model_copy(update={"fields": {k: v for k, v in turn_result.fields.items() if k not in location_names}})
            turn_result = _pin_to_complaint(turn_result, row, keep_fields=True)
        tri = meta.get(triage.STATE_KEY)
        if tri and tri.get("pending") and triage.enabled():  # the answer to a triage question: read it, and never let it overwrite the story or the place
            meta[triage.STATE_KEY] = triage.absorb_reply(tri, bank=_bank(), text=text, recent=recent)
            turn_result = _pin_to_complaint(turn_result, row, keep_fields=False)  # no field changes: "हाँ" must not become the description or the place
        if meta.pop("awaiting_duration", False):  # the answer to "how many days?": the turn engine still reads the number, but it is never chit-chat
            turn_result = _pin_to_complaint(turn_result, row, keep_fields=True)
        pending = meta.get("pending_dept")
        if pending and pending in reg.by_id:  # the citizen's reply to our one yes/no question
            dept = reg.by_id[pending]
            yes = decider.agrees(_state(text, recent), f"The citizen agrees that their problem is about the {dept['name_en']} department.")
            meta["confirmed_by_citizen"] = yes >= AGREE_MIN
            return _route_to(turn_result, dept, specs, reg, meta, "confirmed_by_citizen" if yes >= AGREE_MIN else REASON_UNCONFIRMED)
        if row.service_id is not None and turn_result.intent == "complaint" and not turn_result.confirmed and turn_result.service_id not in (None, row.service_id):
            return _guard_switch(row=row, turn_result=turn_result, text=text, recent=recent, decider=decider, specs=specs, reg=reg, meta=meta)
        if row.service_id is not None or turn_result.intent != "complaint" or turn_result.confirmed:
            return Pre(turn_result, meta if meta else None)  # a complaint already in progress, or not a new complaint: keep the active service
        decision = decider.decide(_state(text, recent), reg.departments)
    except jev.JevUnavailable:
        return Pre(turn_result)  # fail open: the existing LLM path handles this turn
    if not decision.top:
        return Pre(turn_result)
    top_id, _top_p = decision.top[0]
    meta["jev"] = [{"id": i, "p": round(p, 2)} for i, p in decision.top]
    meta["jev_confidence"] = round(decision.confidence, 2)
    turn = turn_result.model_copy(update={"urgent": True}) if decision.urgent >= 0.5 else turn_result
    dept = reg.by_id.get(top_id)
    if dept is None:
        return Pre(turn_result)
    if decision.confidence >= reg.route:
        return _route_to(turn, dept, specs, reg, meta, "confident")
    meta["pending_dept"] = top_id  # one question about the department Jev suggests most
    meta["questions_asked"] = int(meta.get("questions_asked", 0)) + 1
    return Pre(turn, meta, ask=validator._urgent(turn, ASK_PROBLEM_HI.format(dept=dept["name_hi"])), ask_for="service")  # keeps the fixed safety line if urgent


def _guard_switch(*, row: Any, turn_result: TurnResult, text: str, recent: list[Any], decider: jev.Decider, specs: dict[str, ServiceSpec], reg: Registry,
                  meta: dict[str, Any]) -> Pre:
    """The turn engine wants to move a complaint already in progress to another service. It misreads words that appear in several services' hints ("नहीं आ रहा" fits
    water AND "the teacher is not coming"), and a one-word answer such as a village name can flip it too. So only Jev, the department router, may move it, and only when it
    is confident about a different department; otherwise the active service stays. If Jev is down this raises JevUnavailable and the caller fails open as before."""
    decision = decider.decide(_state(text, recent), reg.departments)
    dept = reg.by_id.get(decision.top[0][0]) if decision.top else None
    if dept is not None and decision.confidence >= reg.route and reg.live_specs.get(dept["id"]) != row.service_id:
        meta["jev_switch"] = [{"id": i, "p": round(p, 2)} for i, p in decision.top]
        return _route_to(turn_result, dept, specs, reg, meta, "switched")
    return Pre(_pin_to_complaint(turn_result, row, keep_fields=True), meta if meta else None)


def _pin_to_complaint(turn_result: TurnResult, row: Any, *, keep_fields: bool) -> TurnResult:
    """A reply to a question WE asked belongs to the complaint in progress, whatever the turn engine made of it. It has read "the child's arm is swollen"
    and "I don't know" as chit-chat and sent the out-of-scope reply in the middle of a conversation. Same complaint, not a confirmation."""
    update: dict[str, Any] = {"intent": "complaint", "service_id": row.service_id, "confidence": 1.0, "candidates": [], "confirmed": False}
    if not keep_fields:
        update["fields"] = {}
    return turn_result.model_copy(update=update)


def _bank() -> triage.Bank:
    try:
        return triage.load_bank()
    except Exception:  # a missing or broken bank folder must never block a complaint
        logger.exception("triage bank could not be loaded")
        return {}


def _has_gps(lat: float | None, lng: float | None, row: Any) -> bool:
    return (lat is not None and lng is not None) or (row.lat is not None and row.lng is not None)


def _weak_location(spec: ServiceSpec, fields: dict[str, Any]) -> bool:
    """True when the place the citizen named does not resolve to an office (so a person would have to guess the district)."""
    try:
        location = next(f for f in spec.fields if f.type == "location")
        match = jurisdiction.resolve_office(spec.department, None, None, fields.get(location.name), spec.routing.max_match_distance_km)
        return match.matched_via == "fallback" or match.confidence < spec.routing.min_confidence
    except Exception:  # noqa: BLE001 -- a database hiccup must never block the citizen: skip the extra question
        return False


def _ask(result: validator.ValidationResult, fields: dict[str, Any], reply: str, ask_for: str) -> validator.ValidationResult:
    return result.model_copy(update={"action": validator.ValidatedAction.ASK, "ask_for": ask_for, "reply_text": reply, "summary": None,
                                     "awaiting_confirmation": False, "collected_fields": fields})


def _natural(plain: str, result: validator.ValidationResult, text: str | None, recent: Any, pre: Pre, meta: dict[str, Any], *, must: tuple[str, ...]) -> str:
    """S33c: the district and duration questions in everyday talk (the plain line when triage is off, the LLM is slow, or the reply fails a check)."""
    if not triage.enabled():
        return plain
    try:
        story = str(result.collected_fields.get("description") or "")
        concern = (meta.get(triage.STATE_KEY) or {}).get("severity") in ("high", "urgent")
        return triage._talk().natural(question=plain, fallback=plain, turns=triage._story_turns(story, recent or [], text), concern=concern, index=1, total=3, must_contain=must)
    except Exception:  # the plain line is always good enough
        logger.exception("natural reply failed")
        return plain


def _urgent_line(pre: Pre, meta: dict[str, Any], reply: str) -> str:
    """Triage found an emergency: keep the fixed safety line (S28 Q4) on every question from now on, like an urgent first message."""
    if (meta.get(triage.STATE_KEY) or {}).get("severity") == "urgent":
        return validator._urgent(pre.turn_result.model_copy(update={"urgent": True}), reply)
    return reply


def poststep(*, result: validator.ValidationResult, pre: Pre, specs: dict[str, ServiceSpec], lat: float | None, lng: float | None, row: Any,
             weak_location: Any = None, text: str | None = None, recent: Any = None) -> validator.ValidationResult:
    """After the validator: store the intake notes with the ticket, ask the triage questions (S33), then the location detail and duration once each."""
    if pre.meta is None:
        return result
    meta = dict(pre.meta)
    fields = {**result.collected_fields, META_KEY: meta}
    if result.action is validator.ValidatedAction.CONFIRM and result.service_id in specs:
        spec = specs[result.service_id]
        if triage.enabled():
            try:
                reg = load_registry()
                unconfirmed = meta.get("reason") == REASON_UNCONFIRMED
                # an unconfirmed guess (the citizen said no or "don't know") must not pick the bank's questions: the LLM writes department-free ones instead (hybrid)
                dept_id = None if unconfirmed else triage.dept_for(meta, result.service_id, reg.live_specs)
                dept = reg.by_id.get(dept_id) if dept_id else None
                state, reply, _urgent = triage.step(meta.get(triage.STATE_KEY), bank=_bank(), dept_id=dept_id,
                                                    story=str(result.collected_fields.get("description") or ""), text=text, recent=recent or [],
                                                    dept_name=(dept or {}).get("name_en"), reason=REASON_UNCONFIRMED if unconfirmed else "")
                meta[triage.STATE_KEY] = state
                if reply is not None:
                    return _ask(result, fields, _urgent_line(pre, meta, reply), "triage")
            except Exception:  # triage is an extra: any failure leaves the complaint flowing as before
                logger.exception("triage step failed")
        probe = weak_location or _weak_location
        if not _has_gps(lat, lng, row) and not meta.get("asked_location_detail") and probe(spec, result.collected_fields):
            meta["asked_location_detail"] = meta["awaiting_location_detail"] = True
            ask = _natural(ASK_LOCATION_DETAIL_HI, result, text, recent, pre, meta, must=("जिला", "तहसील"))
            return _ask(result, fields, _urgent_line(pre, meta, ask), "location_detail")
        if spec.field("duration_days") is not None and "duration_days" not in result.collected_fields and not meta.get("asked_duration"):
            meta["asked_duration"] = meta["awaiting_duration"] = True
            ask = _natural(ASK_DURATION_HI, result, text, recent, pre, meta, must=("पता नहीं",))
            return _ask(result, fields, _urgent_line(pre, meta, ask), "duration_days")
    return result.model_copy(update={"collected_fields": fields})
