"""S09 Jurisdiction resolver (T16): every BEHAVIOR branch and tie-break, against a minimal fake
offices client -- no network, no real credentials.
"""

from types import SimpleNamespace

import pytest

from app.jurisdiction import JurisdictionError, resolve_office

DEPARTMENT = "Jal Vibhag"


class _OfficesQuery:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.filters: dict = {}

    def select(self, *_cols):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def execute(self):
        matched = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())]
        return SimpleNamespace(data=matched)


class FakeOfficesClient:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def table(self, name):
        assert name == "offices"
        return _OfficesQuery(self.rows)


def ward(id, name, aliases=None, centroid_lat=None, centroid_lng=None) -> dict:
    return {
        "id": id,
        "level": "ward",
        "name": name,
        "aliases": aliases or [],
        "centroid_lat": centroid_lat,
        "centroid_lng": centroid_lng,
        "office_name": f"Ward {name} Office",
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


def with_department(rows: list[dict]) -> list[dict]:
    return [{**r, "department": DEPARTMENT, "active": True} for r in rows]


# --- GPS ---------------------------------------------------------------------------------------


def test_gps_within_range_matches_nearest_ward():
    rows = with_department(
        [
            ward(1, "Misrod", centroid_lat=23.20, centroid_lng=77.43),
            ward(2, "Govindpura", centroid_lat=23.28, centroid_lng=77.45),
        ]
    ) + [DISTRICT]
    client = FakeOfficesClient(rows)

    match = resolve_office(DEPARTMENT, 23.201, 77.431, None, 5.0, client=client)

    assert match.matched_via == "gps"
    assert match.confidence == 1.0
    assert match.office.id == 1


def test_gps_tie_falls_through():
    rows = with_department(
        [
            ward(1, "Misrod", centroid_lat=23.20, centroid_lng=77.43),
            ward(2, "Govindpura", centroid_lat=23.20, centroid_lng=77.43),  # identical centroid
        ]
    ) + [DISTRICT]
    client = FakeOfficesClient(rows)

    match = resolve_office(DEPARTMENT, 23.20, 77.43, None, 5.0, client=client)

    assert match.matched_via == "fallback"
    assert match.confidence == 0.0


def test_gps_too_far_falls_through():
    rows = with_department([ward(1, "Misrod", centroid_lat=23.20, centroid_lng=77.43)]) + [DISTRICT]
    client = FakeOfficesClient(rows)

    match = resolve_office(DEPARTMENT, 24.50, 78.50, None, 5.0, client=client)

    assert match.matched_via == "fallback"


def test_no_ward_centroids_falls_through_to_name():
    rows = with_department([ward(1, "Misrod", aliases=["Misrod"])]) + [DISTRICT]
    client = FakeOfficesClient(rows)

    match = resolve_office(DEPARTMENT, 23.20, 77.43, "Misrod", 5.0, client=client)

    assert match.matched_via == "name"
    assert match.office.id == 1


# --- Name --------------------------------------------------------------------------------------


def test_name_match_above_threshold():
    rows = with_department([ward(1, "Misrod", aliases=["Misrod"])]) + [DISTRICT]
    client = FakeOfficesClient(rows)

    match = resolve_office(DEPARTMENT, None, None, "Misrod", 5.0, client=client)

    assert match.matched_via == "name"
    assert match.confidence >= 0.8
    assert match.office.id == 1


def test_name_no_match_falls_back():
    rows = with_department([ward(1, "Misrod", aliases=["Misrod"])]) + [DISTRICT]
    client = FakeOfficesClient(rows)

    match = resolve_office(DEPARTMENT, None, None, "xyz totally unrelated", 5.0, client=client)

    assert match.matched_via == "fallback"
    assert match.confidence == 0.0


def test_name_tie_falls_back():
    rows = with_department(
        [
            ward(1, "Misrod", aliases=["Kolar"]),
            ward(2, "Govindpura", aliases=["Kolar"]),  # identical alias -> identical score
        ]
    ) + [DISTRICT]
    client = FakeOfficesClient(rows)

    match = resolve_office(DEPARTMENT, None, None, "Kolar", 5.0, client=client)

    assert match.matched_via == "fallback"


# --- Precedence and fallback ---------------------------------------------------------------------


def test_gps_takes_precedence_over_place_name():
    rows = with_department(
        [
            ward(1, "Misrod", centroid_lat=23.20, centroid_lng=77.43, aliases=["Misrod"]),
            ward(2, "Govindpura", aliases=["Govindpura"]),
        ]
    ) + [DISTRICT]
    client = FakeOfficesClient(rows)

    match = resolve_office(DEPARTMENT, 23.201, 77.431, "Govindpura", 5.0, client=client)

    assert match.matched_via == "gps"
    assert match.office.id == 1


def test_no_gps_no_place_name_goes_straight_to_fallback():
    rows = with_department([ward(1, "Misrod", aliases=["Misrod"])]) + [DISTRICT]
    client = FakeOfficesClient(rows)

    match = resolve_office(DEPARTMENT, None, None, None, 5.0, client=client)

    assert match.matched_via == "fallback"
    assert match.confidence == 0.0
    assert match.office.office_name == "BMC Head Office"


def test_no_active_district_raises():
    rows = with_department([ward(1, "Misrod", aliases=["Misrod"])])
    client = FakeOfficesClient(rows)

    with pytest.raises(JurisdictionError):
        resolve_office(DEPARTMENT, None, None, "Misrod", 5.0, client=client)


# --- S31: legacy desk fallback ----------------------------------------------------------------


def test_human_evaluation_falls_back_to_legacy_general_triage_desk():
    legacy = {**DISTRICT, "id": 7, "department": "General Triage", "office_name": "Triage Desk"}
    office = resolve_office("Human Evaluation", None, None, None, 5, client=FakeOfficesClient([legacy]))
    assert office.office.id == 7


def test_human_evaluation_prefers_its_own_desk_when_present():
    legacy = {**DISTRICT, "id": 7, "department": "General Triage"}
    new = {**DISTRICT, "id": 8, "department": "Human Evaluation"}
    office = resolve_office("Human Evaluation", None, None, None, 5, client=FakeOfficesClient([legacy, new]))
    assert office.office.id == 8


def test_other_departments_never_fall_back():
    legacy = {**DISTRICT, "id": 7, "department": "General Triage"}
    with pytest.raises(JurisdictionError):
        resolve_office(DEPARTMENT, None, None, None, 5, client=FakeOfficesClient([legacy]))
