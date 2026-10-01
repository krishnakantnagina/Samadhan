"""Citizen-facing field labels from specs/water_supply.yaml, for the detail panel (S14 D-S14-1).
No cross-project YAML loader for one hackathon ticket -- these 4 fields are stable (S03: field
names are the API contract). If specs/water_supply.yaml's labels change, update here too.
"""

from typing import Any

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


def display_field(name: str, value: Any) -> tuple[str, str]:
    """(label, display value) for one fields[name] entry -- issue_type's value gets its own
    label lookup, everything else is shown as-is."""
    label = FIELD_LABELS_EN.get(name, name)
    if name == "issue_type":
        return label, ISSUE_TYPE_LABELS_EN.get(value, str(value))
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
        out.append(f"**Why:** {INTAKE_REASON_EN.get(meta['reason'], meta['reason'])}")
    sug = meta.get("suggested_department")
    if isinstance(sug, dict):
        out.append(f"**Suggested department:** {sug.get('name_en', '?')} ({sug.get('name_hi', '')})")
    jev = meta.get("jev")
    if isinstance(jev, list) and jev:
        out.append("**Jev's top choices:** " + ", ".join(f"{c.get('id')} {round(float(c.get('p', 0)) * 100)}%" for c in jev))
    if "questions_asked" in meta:
        out.append(f"**Department questions asked:** {meta['questions_asked']}")
    loc = meta.get("location_details")
    if isinstance(loc, dict) and loc:
        if loc.get("unknown") and not (loc.get("district") or loc.get("tehsil") or loc.get("nearest_place")):
            out.append("**District / tehsil / nearest place:** the citizen did not know")
        else:
            parts = [f"district {loc['district']}" if loc.get("district") else None, f"tehsil {loc['tehsil']}" if loc.get("tehsil") else None,
                     f"near {loc['nearest_place']}" if loc.get("nearest_place") else None]
            out.append("**District / tehsil / nearest place:** " + ", ".join(p for p in parts if p))
    elif meta.get("location_detail"):  # notes written before S31
        out.append(f"**Citizen's district / tehsil / nearest place:** {meta['location_detail']}")
    return out
