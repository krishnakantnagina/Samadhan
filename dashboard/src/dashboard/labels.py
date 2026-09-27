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
}

ISSUE_TYPE_LABELS_EN = {
    "no_supply": "No water supply",
    "low_pressure": "Low pressure",
    "dirty_water": "Dirty or smelly water",
    "leakage": "Pipe or tap leakage",
    "other": "Other water issue",
}


def display_field(name: str, value: Any) -> tuple[str, str]:
    """(label, display value) for one fields[name] entry -- issue_type's value gets its own
    label lookup, everything else is shown as-is."""
    label = FIELD_LABELS_EN.get(name, name)
    if name == "issue_type":
        return label, ISSUE_TYPE_LABELS_EN.get(value, str(value))
    return label, str(value)
