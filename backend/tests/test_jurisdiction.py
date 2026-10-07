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


# --- district-aware routing (migration 005) ---------------------------------------------------------


def in_district(row: dict, district: str | None) -> dict:
    return {**row, "district": district}


def multi_district_offices() -> list[dict]:
    """The same village name in two districts, plus a district desk for each, and a default desk with no district."""
    return with_department(
        [
            in_district(ward(1, "Rampur"), "Bhopal"),
            in_district(ward(2, "Rampur"), "Rewa"),
            in_district({**DISTRICT, "id": 10, "office_name": "Bhopal desk"}, "Bhopal"),
            in_district({**DISTRICT, "id": 11, "office_name": "Rewa desk", "name": "Rewa"}, "Rewa"),
        ]
    )


def test_a_place_name_is_matched_only_inside_the_citizens_district():
    client = FakeOfficesClient(multi_district_offices())
    match = resolve_office(DEPARTMENT, None, None, "Rampur", 5.0, district="Rewa", client=client)
    assert (match.office.id, match.matched_via) == (2, "name")  # the Rewa ward, not the Bhopal one


def test_the_districts_own_office_is_used_when_no_ward_matches():
    client = FakeOfficesClient(multi_district_offices())
    match = resolve_office(DEPARTMENT, None, None, "somewhere unknown", 5.0, district="Rewa", client=client)
    assert (match.office.id, match.matched_via, match.confidence) == (11, "district", 0.7)


def test_district_names_are_compared_ignoring_case_and_spaces():
    client = FakeOfficesClient(multi_district_offices())
    match = resolve_office(DEPARTMENT, None, None, None, 5.0, district="  rewa ", client=client)
    assert match.office.id == 11


def test_a_district_without_an_office_falls_back_to_the_default_desk_for_review():
    client = FakeOfficesClient(multi_district_offices())
    match = resolve_office(DEPARTMENT, None, None, "Rampur", 5.0, district="Rajgarh", client=client)
    assert match.matched_via == "fallback" and match.confidence == 0.0


def test_unknown_district_in_a_multi_district_department_never_matches_a_name():
    client = FakeOfficesClient(multi_district_offices())
    match = resolve_office(DEPARTMENT, None, None, "Rampur", 5.0, client=client)  # no district given
    assert match.matched_via == "fallback"  # "Rampur" exists in two districts: do not guess


def test_gps_still_finds_the_nearest_ward_when_the_district_is_unknown():
    rows = with_department(
        [
            in_district(ward(1, "Rampur", centroid_lat=23.20, centroid_lng=77.40), "Bhopal"),
            in_district(ward(2, "Rampur", centroid_lat=24.53, centroid_lng=81.30), "Rewa"),
            in_district({**DISTRICT, "id": 10}, "Bhopal"),
            in_district({**DISTRICT, "id": 11, "name": "Rewa"}, "Rewa"),
        ]
    )
    match = resolve_office(DEPARTMENT, 24.531, 81.301, None, 5.0, client=FakeOfficesClient(rows))
    assert (match.office.id, match.matched_via) == (2, "gps")


def test_offices_without_a_district_value_behave_as_before_for_any_district():
    # an older database (migration 005 not applied): rows carry no district, the citizen still names one
    rows = with_department([ward(1, "Misrod"), DISTRICT])
    match = resolve_office(DEPARTMENT, None, None, "Misrod", 5.0, district="Bhopal", client=FakeOfficesClient(rows))
    assert (match.office.id, match.matched_via) == (1, "name")


def test_a_database_without_the_district_column_still_routes():
    rows = with_department([ward(1, "Misrod"), DISTRICT])

    class NoDistrictColumn(FakeOfficesClient):
        def table(self, name):
            query = super().table(name)
            real_select = query.select

            def select(cols="", *_):
                if "district" in cols.split(","):
                    raise RuntimeError("column offices.district does not exist")
                return real_select(cols)

            query.select = select
            return query

    match = resolve_office(DEPARTMENT, None, None, "Misrod", 5.0, district="Bhopal", client=NoDistrictColumn(rows))
    assert match.office.id == 1
