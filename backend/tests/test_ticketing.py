"""S10 Ticket + routing (T17): create_ticket against a minimal fake client covering both `offices`
(for the internal resolve_office call) and `tickets` (with generated complaint_id simulation).
"""

import uuid
from types import SimpleNamespace

import pytest

from app.schemas import ComplaintStatus, OfficeLevel
from app.service_spec import ServiceSpec
from app.ticketing import TicketingError, create_ticket

DEPARTMENT = "Jal Vibhag"


def make_spec(min_confidence: float = 0.7) -> ServiceSpec:
    return ServiceSpec.model_validate(
        {
            "spec_version": 1,
            "service": "water_supply",
            "department": DEPARTMENT,
            "label": {"hi": "पानी", "en": "Water"},
            "recognise": ["no water"],
            "out_of_scope": {
                "examples": ["electricity"],
                "reply": {"hi": "क्षमा करें", "en": "Sorry"},
            },
            "pilot": {"city": "Bhopal", "wards": 5},
            "routing": {
                "min_confidence": min_confidence,
                "fallback_level": "district",
                "fallback_status": "needs_review",
                "max_match_distance_km": 5,
            },
            "confirmation": "required",
            "fields": [
                {
                    "name": "issue_type",
                    "type": "enum",
                    "required": True,
                    "label": {"hi": "समस्या", "en": "Issue"},
                    "question": {"hi": "समस्या?", "en": "Problem?"},
                    "values": [
                        {"value": "no_supply", "hi": "पानी नहीं", "en": "No water"},
                        {"value": "leakage", "hi": "लीकेज", "en": "Leakage"},
                    ],
                },
                {
                    "name": "location",
                    "type": "location",
                    "required": True,
                    "label": {"hi": "स्थान", "en": "Location"},
                    "question": {"hi": "स्थान?", "en": "Where?"},
                    "accepts": {
                        "gps": {"lat": [-90, 90], "lng": [-180, 180]},
                        "place_name": {"min_length": 2, "max_length": 100},
                    },
                },
                {
                    "name": "duration_days",
                    "type": "integer",
                    "required": False,
                    "min": 0,
                    "max": 365,
                    "label": {"hi": "दिन", "en": "Days affected"},
                },
            ],
        }
    )


SPEC = make_spec()


def ward(id, name, aliases=None, centroid_lat=None, centroid_lng=None) -> dict:
    return {
        "id": id,
        "level": "ward",
        "name": name,
        "aliases": aliases or [],
        "centroid_lat": centroid_lat,
        "centroid_lng": centroid_lng,
        "office_name": f"Ward {name} Office",
        "department": DEPARTMENT,
        "active": True,
    }


DISTRICT = {
    "id": 99,
    "level": "district",
    "name": "Bhopal",
    "aliases": ["BMC"],
    "centroid_lat": None,
    "centroid_lng": None,
    "office_name": "BMC Head Office",
    "department": DEPARTMENT,
    "active": True,
}


class _Query:
    def __init__(self, fake, table_name):
        self.fake = fake
        self.table_name = table_name
        self.filters: dict = {}
        self.op = None
        self.payload = None

    def select(self, *_cols):
        self.op = "select"
        return self

    def insert(self, row):
        self.op = "insert"
        self.payload = row
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def execute(self):
        if self.op == "insert":
            self.fake.next_id += 1
            row = dict(self.payload)
            row["id"] = self.fake.next_id
            row["complaint_id"] = f"SMD-{self.fake.next_id:04d}"
            self.fake.tables.setdefault(self.table_name, []).append(row)
            return SimpleNamespace(data=[row])

        rows = self.fake.tables.get(self.table_name, [])
        matched = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
        return SimpleNamespace(data=matched)


class FakeClient:
    def __init__(self, offices: list[dict]):
        self.tables = {"offices": offices, "tickets": []}
        self.next_id = 0

    def table(self, name):
        return _Query(self, name)


def call_create_ticket(client, spec=SPEC, **overrides):
    args = {
        "session_id": uuid.uuid4(),
        "spec": spec,
        "validated_fields": {"issue_type": "no_supply", "location": "Misrod"},
        "lat": None,
        "lng": None,
        "original_text": "no water since 3 days",
        "audio_path": None,
        "client": client,
    }
    args.update(overrides)
    return create_ticket(**args)


# --- routing status --------------------------------------------------------------------------


def test_gps_match_creates_new_status_ticket():
    client = FakeClient([ward(1, "Misrod", centroid_lat=23.20, centroid_lng=77.43), DISTRICT])

    ticket = call_create_ticket(
        client, lat=23.201, lng=77.431, validated_fields={"issue_type": "no_supply"}
    )

    assert ticket.status == ComplaintStatus.NEW
    assert ticket.office.level == OfficeLevel.WARD
    assert ticket.complaint_id.startswith("SMD-")
    import re

    assert re.fullmatch(r"SMD-\d{4,}", ticket.complaint_id)


def test_unknown_location_creates_needs_review_district_ticket():
    client = FakeClient([ward(1, "Misrod", aliases=["Misrod"]), DISTRICT])

    ticket = call_create_ticket(
        client, validated_fields={"issue_type": "no_supply", "location": "Nowhere"}
    )

    assert ticket.status == ComplaintStatus.NEEDS_REVIEW
    assert ticket.office.level == OfficeLevel.DISTRICT
    assert ticket.office.name == "BMC Head Office"


def test_name_match_below_custom_min_confidence_is_still_needs_review():
    spec = make_spec(min_confidence=0.95)  # a near-exact (not exact) alias match scores ~0.92,
    # above NAME_MATCH_MIN_SCORE's 0.8 floor but below this spec's own 0.95 -- exercises the
    # `confidence < min_confidence` check on its own, not the redundant `matched_via == "fallback"`
    # half (D-S10-3)
    client = FakeClient([ward(1, "Misrod", aliases=["Misrod"]), DISTRICT])

    ticket = call_create_ticket(
        client, spec=spec, validated_fields={"issue_type": "no_supply", "location": "Misrode"}
    )

    assert ticket.status == ComplaintStatus.NEEDS_REVIEW
    assert ticket.office.level == OfficeLevel.WARD  # still routed to the matched ward, just flagged


# --- summary_en --------------------------------------------------------------------------------


def test_summary_en_includes_english_labels_and_values():
    client = FakeClient([ward(1, "Misrod", aliases=["Misrod"]), DISTRICT])

    call_create_ticket(
        client,
        validated_fields={"issue_type": "no_supply", "location": "Misrod", "duration_days": 3},
    )

    [ticket_row] = client.tables["tickets"]
    assert "Issue: No water" in ticket_row["summary_en"]
    assert "Days affected: 3" in ticket_row["summary_en"]


def test_summary_en_uses_coordinates_for_gps_location():
    client = FakeClient([ward(1, "Misrod", centroid_lat=23.20, centroid_lng=77.43), DISTRICT])

    call_create_ticket(client, lat=23.201, lng=77.431, validated_fields={"issue_type": "no_supply"})

    [ticket_row] = client.tables["tickets"]
    assert "23.201, 77.431" in ticket_row["summary_en"]


# --- ticket row content -------------------------------------------------------------------------


def test_ticket_fields_column_matches_validated_fields_exactly():
    client = FakeClient([ward(1, "Misrod", aliases=["Misrod"]), DISTRICT])
    validated = {"issue_type": "no_supply", "location": "Misrod", "duration_days": 3}

    call_create_ticket(client, validated_fields=validated)

    [ticket_row] = client.tables["tickets"]
    assert ticket_row["fields"] == validated
    assert ticket_row["original_text"] == "no water since 3 days"
    assert ticket_row["audio_path"] is None


def test_spec_without_location_field_raises():
    bad_spec = ServiceSpec.model_validate(
        {
            "spec_version": 1,
            "service": "no_location_service",
            "department": DEPARTMENT,
            "label": {"hi": "x", "en": "x"},
            "recognise": ["x"],
            "out_of_scope": {"examples": ["y"], "reply": {"hi": "x", "en": "x"}},
            "pilot": {"city": "Bhopal", "wards": 5},
            "routing": {
                "min_confidence": 0.7,
                "fallback_level": "district",
                "fallback_status": "needs_review",
                "max_match_distance_km": 5,
            },
            "confirmation": "required",
            "fields": [
                {
                    "name": "issue_type",
                    "type": "enum",
                    "required": True,
                    "label": {"hi": "x", "en": "x"},
                    "question": {"hi": "x", "en": "x"},
                    "values": [
                        {"value": "a", "hi": "x", "en": "x"},
                        {"value": "b", "hi": "y", "en": "y"},
                    ],
                }
            ],
        }
    )
    client = FakeClient([DISTRICT])

    with pytest.raises(TicketingError):
        call_create_ticket(client, spec=bad_spec, validated_fields={"issue_type": "a"})
