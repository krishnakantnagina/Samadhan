"""Field and issue labels for the officer screens.

Issue-type labels come from the service specs themselves (`specs/<service>.yaml`, every department), keyed by (service_id, value): the value `other` exists in
46 departments and must read "Other ..." of THAT department, not "Other water issue". The small hand-written table below is the fallback for a database
that has no `specs/` folder next to it (and for tickets filed before service_id was recorded).
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from dashboard.safe import md

FIELD_LABELS_EN = {
    "issue_type": "Issue",
    "location": "Location",
    "duration_days": "Days affected",
    "address_detail": "Address or landmark",
    "description": "Complaint",  # S28 general triage
}

ISSUE_TYPE_LABELS_EN = {
    "no_supply": "No water supply",
    "low_pressure": "Low pressure",
    "dirty_water": "Dirty or smelly water",
    "leakage": "Pipe or tap leakage",
    "other": "Other water issue",
    # S28 departments (enum values are unique across specs so one map serves all of them)
    "no_power": "No power",
    "low_voltage": "Low or high voltage",
    "pole_wire": "Pole, wire or transformer",
    "billing": "Bill or meter problem",
    "power_other": "Other electricity issue",
    "pothole": "Pothole",
    "broken_road": "Broken road or culvert",
    "road_other": "Other road issue",
    "garbage": "Garbage not collected",
    "drain_blocked": "Drain blocked or overflowing",
    "dirty_area": "Dirty area",
    "sanitation_other": "Other sanitation issue",
}


def _specs_dir() -> Path:
    return Path(os.environ.get("SPECS_DIR") or Path(__file__).resolve().parents[3] / "specs")


@lru_cache(maxsize=1)
def _spec_labels() -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """({(service_id, value): English label}, {value: label} for values only ONE service uses). Empty when the specs folder is not there."""
    by_service: dict[tuple[str, str], str] = {}
    owners: dict[str, set[str]] = {}
    try:
        for path in sorted(_specs_dir().glob("*.yaml")):
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
            for field in spec.get("fields", []):
                if field.get("name") != "issue_type":
                    continue
                for v in field.get("values", []):
                    by_service[(spec["service"], v["value"])] = v["en"]
                    owners.setdefault(v["value"], set()).add(spec["service"])
    except (OSError, yaml.YAMLError, KeyError, TypeError):
        return {}, {}
    unique = {value: by_service[(next(iter(svcs)), value)] for value, svcs in owners.items() if len(svcs) == 1}
    return by_service, unique


def issue_label(value: Any, service_id: str | None = None) -> str:
    """The English label of an issue_type value, in the language an officer reads. Never raises; falls back to the raw value, tidied."""
    by_service, unique = _spec_labels()
    if service_id and (service_id, value) in by_service:
        return by_service[(service_id, value)]
    if value in unique:
        return unique[value]
    if value in ISSUE_TYPE_LABELS_EN and value != "other":  # "other" alone is ambiguous: say so rather than guess a department
        return ISSUE_TYPE_LABELS_EN[value]
    return str(value).replace("_", " ").capitalize() if value else "-"


def display_field(name: str, value: Any, service_id: str | None = None) -> tuple[str, str]:
    """(label, display value) for one fields[name] entry -- issue_type's value gets its own
    label lookup, everything else is shown as-is."""
    label = FIELD_LABELS_EN.get(name, name)
    if name == "issue_type":
        return label, issue_label(value, service_id)
    return label, str(value)


INTAKE_REASON_EN = {
    "confident": "Jev was confident about the department",
    "confirmed_by_citizen": "Jev was unsure; the citizen confirmed the suggested department",
    "department_not_live": "Jev is sure of the department, but it has no service spec or offices yet, so a person must assign it",
    "department_unconfirmed": "Jev was unsure and the citizen did not confirm the suggested department: needs a person",
}


def intake_notes(meta: Any) -> list[str]:
    """Readable lines from a ticket's fields["_intake"] (written by backend/app/intake.py, S30). Empty when the ticket predates intake v2."""
    if not isinstance(meta, dict) or not meta:
        return []
    out = []
    if meta.get("reason"):
        out.append(f"**Why:** {md(INTAKE_REASON_EN.get(meta['reason'], meta['reason']))}")
    sug = meta.get("suggested_department")
    if isinstance(sug, dict):
        out.append(f"**Suggested department:** {md(sug.get('name_en', '?'))} ({md(sug.get('name_hi', ''))})")
    jev = meta.get("jev")
    if isinstance(jev, list) and jev:
        out.append("**Jev's top choices:** " + ", ".join(f"{md(c.get('id'))} {round(float(c.get('p', 0)) * 100)}%" for c in jev))
    if "questions_asked" in meta:
        out.append(f"**Department questions asked:** {meta['questions_asked']}")
    loc = meta.get("location_details")
    if isinstance(loc, dict) and loc:
        if loc.get("unknown") and not (loc.get("district") or loc.get("tehsil") or loc.get("nearest_place")):
            out.append("**District / tehsil / nearest place:** the citizen did not know")
        else:
            parts = [f"district {md(loc['district'])}" if loc.get("district") else None, f"tehsil {md(loc['tehsil'])}" if loc.get("tehsil") else None,
                     f"near {md(loc['nearest_place'])}" if loc.get("nearest_place") else None]
            out.append("**District / tehsil / nearest place:** " + ", ".join(p for p in parts if p))
    elif meta.get("location_detail"):  # notes written before S31
        out.append(f"**Citizen's district / tehsil / nearest place:** {md(meta['location_detail'])}")
    return out
