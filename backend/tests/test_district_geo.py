"""GPS point -> district, state-level desks, and the GPS shared in an earlier message still counting at the confirm turn."""

import json
import uuid
from types import SimpleNamespace

import pytest

from app import district_geo, ticketing
from app.jurisdiction import resolve_office
from tests.test_jurisdiction import DEPARTMENT, DISTRICT, FakeOfficesClient, ward, with_department

SQUARE = [[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]]
HOLE = [[3.0, 3.0], [6.0, 3.0], [6.0, 6.0], [3.0, 6.0], [3.0, 3.0]]


@pytest.fixture
def geo_file(tmp_path):
    data = {
        "districts": {
            "Squareville": {"bbox": [0, 0, 10, 10], "centre": [5.0, 5.0], "polygons": [SQUARE]},
            "Donutville": {"bbox": [20, 0, 30, 10], "centre": [25.0, 5.0], "polygons": [[[[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]], [[23, 3], [26, 3], [26, 6], [23, 6], [23, 3]]]]},
            "Pointville": {"centre": [50.0, 50.0], "polygons": []},  # a district OpenStreetMap has no boundary for: centre only
        }
    }
    path = tmp_path / "geo.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    district_geo.load.cache_clear()
    return str(path)


def test_a_point_inside_a_polygon_is_that_district(geo_file):
    assert district_geo.district_for(2.0, 2.0, path=geo_file) == "Squareville"


def test_a_hole_is_not_part_of_the_district_and_falls_to_the_nearest_centre(geo_file):
    # lat 4.5, lng 24.5 is inside Donutville's hole: no polygon contains it, the nearest centre (25, 5) is 0.7 degrees away (~80 km): too far
    assert district_geo.district_for(4.5, 24.5, path=geo_file) is None
    assert district_geo.district_for(1.0, 21.0, path=geo_file) == "Donutville"  # solid part of the ring


def test_a_district_with_only_a_centre_gets_nearby_points(geo_file):
    assert district_geo.district_for(50.1, 50.1, path=geo_file) == "Pointville"
    assert district_geo.district_for(52.0, 52.0, path=geo_file) is None  # about 300 km away


def test_nowhere_near_anything_is_none_and_bad_input_never_raises(geo_file):
    assert district_geo.district_for(-40.0, 100.0, path=geo_file) is None
    assert district_geo.district_for(None, 77.0, path=geo_file) is None
    assert district_geo.district_for(999, 999, path=geo_file) is None
    assert district_geo.district_for(1.0, 1.0, path="/no/such/file.json") is None


@pytest.mark.parametrize(
    ("place", "lat", "lng", "expected"),
    [
        ("Bhopal", 23.2599, 77.4126, "Bhopal"),
        ("Indore", 22.7196, 75.8577, "Indore"),
        ("Rajgarh town", 24.0059, 76.7285, "Rajgarh"),
        ("Maihar (new district, 2023)", 24.2630, 80.7590, "Maihar"),
        ("Pandhurna (new district, 2023)", 21.6040, 78.5240, "Pandhurna"),
        ("Mauganj (new district, 2023)", 24.6860, 81.8860, "Mauganj"),
        ("Agar town", 23.7120, 76.0150, "Agar Malwa"),
        ("Nagpur, Maharashtra", 21.1458, 79.0882, None),
        ("Kota, Rajasthan", 25.2138, 75.8648, None),
    ],
)
def test_the_shipped_boundaries_find_known_places(place, lat, lng, expected):
    assert district_geo.district_for(lat, lng) == expected, place


def test_the_shipped_file_covers_all_55_districts_with_the_names_the_rest_of_the_system_uses():
    import yaml

    from app import location_details

    names = {d["name_en"] for d in yaml.safe_load(location_details.DISTRICTS_PATH.read_text(encoding="utf-8"))["districts"]}
    geo = district_geo.load()
    assert set(geo) == names and len(names) == 55
    assert all(d["polygons"] for d in geo.values())


# --- state desks ----------------------------------------------------------------------------------------------


def state_desk(id=900):
    return {"id": id, "level": "state", "name": "State", "aliases": [], "centroid_lat": None, "centroid_lng": None, "office_name": "State desk (Bhopal)", "department": DEPARTMENT, "active": True, "district": None}


def test_a_state_level_department_routes_every_complaint_to_its_state_desk_with_confidence():
    client = FakeOfficesClient([state_desk()])
    for district in (None, "Rewa", "Rajgarh"):
        match = resolve_office(DEPARTMENT, None, None, "somewhere", 5.0, district=district, client=client)
        assert (match.office.id, match.matched_via, match.confidence) == (900, "state", 0.7)


def test_a_district_without_its_own_desk_goes_to_the_state_desk_when_there_is_one():
    rows = with_department([{**DISTRICT, "id": 10, "district": "Bhopal"}]) + [state_desk()]
    match = resolve_office(DEPARTMENT, None, None, None, 5.0, district="Rewa", client=FakeOfficesClient(rows))
    assert match.matched_via == "state"


def test_with_the_district_unknown_and_district_desks_existing_the_bot_still_asks_for_the_district():
    rows = with_department([{**DISTRICT, "id": 10, "district": "Bhopal"}]) + [state_desk()]
    match = resolve_office(DEPARTMENT, None, None, None, 5.0, client=FakeOfficesClient(rows))
    assert match.matched_via == "fallback"  # "fallback" is what makes intake ask for the district


def test_the_districts_own_desk_beats_the_state_desk():
    rows = with_department([{**DISTRICT, "id": 11, "district": "Rewa", "name": "Rewa"}]) + [state_desk()]
    match = resolve_office(DEPARTMENT, None, None, None, 5.0, district="Rewa", client=FakeOfficesClient(rows))
    assert (match.office.id, match.matched_via) == (11, "district")


def test_a_department_with_neither_still_raises():
    from app.jurisdiction import JurisdictionError

    with pytest.raises(JurisdictionError):
        resolve_office(DEPARTMENT, None, None, None, 5.0, client=FakeOfficesClient(with_department([ward(1, "Misrod")])))


# --- the district from a shared GPS point reaches routing, and the earlier GPS counts ---------------------------


def test_create_ticket_uses_the_district_found_from_gps(monkeypatch):
    seen = {}

    def fake_resolve(**kwargs):
        seen.update(kwargs)
        from app.jurisdiction import JurisdictionMatch, OfficeRef
        from app.schemas import OfficeLevel

        return JurisdictionMatch(OfficeRef(1, OfficeLevel.DISTRICT, "Rajgarh desk"), 0.7, "district")

    monkeypatch.setattr(ticketing.jurisdiction, "resolve_office", fake_resolve)
    monkeypatch.setattr(ticketing, "_existing_ticket", lambda *a, **k: None)
    from tests.test_ticketing import SPEC, FakeClient

    client = FakeClient([])
    ticketing.create_ticket(
        session_id=uuid.uuid4(), spec=SPEC, validated_fields={"issue_type": "no_supply", "location": "Kiloda"}, lat=24.0059, lng=76.7285,
        original_text="x", audio_path=None, client=client,
    )
    assert seen["district"] == "Rajgarh"


def test_a_district_the_citizen_typed_wins_over_the_one_found_from_gps(monkeypatch):
    seen = {}
    from app.jurisdiction import JurisdictionMatch, OfficeRef
    from app.schemas import OfficeLevel

    monkeypatch.setattr(
        ticketing.jurisdiction, "resolve_office",
        lambda **kw: (seen.update(kw), JurisdictionMatch(OfficeRef(1, OfficeLevel.DISTRICT, "d"), 0.7, "district"))[1],
    )
    monkeypatch.setattr(ticketing, "_existing_ticket", lambda *a, **k: None)
    from tests.test_ticketing import SPEC, FakeClient

    fields = {"issue_type": "no_supply", "location": "Kiloda", "_intake": {"location_details": {"district": "Sagar"}}}
    ticketing.create_ticket(session_id=uuid.uuid4(), spec=SPEC, validated_fields=fields, lat=24.0059, lng=76.7285, original_text="x", audio_path=None, client=FakeClient([]))
    assert seen["district"] == "Sagar"


def test_the_confirm_turn_uses_the_gps_shared_earlier_in_the_chat(monkeypatch):
    """The website sends GPS once; the later "haan" has none. The ticket must still carry it (it used to be lost)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import routes, turn_engine, validator
    from mock.errors import register_error_handlers
    from tests.test_routes import SPEC, make_session_row

    seen = {}
    monkeypatch.setattr(routes.session, "get_or_create_session", lambda sid: make_session_row(id=sid, lat=24.0059, lng=76.7285))
    monkeypatch.setattr(routes.session, "find_stored_response", lambda sid, mid: None)
    monkeypatch.setattr(routes.session, "get_recent_messages", lambda sid, limit=4: [])
    monkeypatch.setattr(routes.session, "save_turn", lambda **kw: None)
    monkeypatch.setattr(routes.turn_engine, "run_turn", lambda **kw: turn_engine.TurnResult(service_id="water_supply", fields={}, confirmed=True))
    monkeypatch.setattr(
        routes.validator, "apply",
        lambda **kw: validator.ValidationResult(
            service_id="water_supply", collected_fields={"issue_type": "no_supply"}, awaiting_confirmation=False,
            action=validator.ValidatedAction.READY_TO_SUBMIT, ask_for=None, reply_text=None, summary={"issue_type": "x"},
        ),
    )
    monkeypatch.setattr(
        routes.ticketing, "create_ticket",
        lambda **kw: (seen.update(kw), SimpleNamespace(complaint_id="SMD-0001", department="d", office=SimpleNamespace(name="o", level="district"), status="new"))[1],
    )
    app = FastAPI()
    register_error_handlers(app)
    app.state.specs = {SPEC.service: SPEC}
    app.include_router(routes.router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    client.post("/api/v1/message", data={"session_id": str(uuid.uuid4()), "message_id": str(uuid.uuid4()), "text": "haan"})

    assert (seen["lat"], seen["lng"]) == (24.0059, 76.7285)


# --- the district found from GPS is also stored on the ticket (for the dashboards' area analysis) ---------------


def test_the_ticket_stores_the_district_found_from_gps_with_exact_precision():
    from tests.test_ticketing import DISTRICT, SPEC, FakeClient

    client = FakeClient([{**DISTRICT, "district": "Rajgarh", "name": "Rajgarh"}])
    ticketing.create_ticket(
        session_id=uuid.uuid4(), spec=SPEC, validated_fields={"issue_type": "no_supply", "location": "Kiloda"}, lat=24.0059, lng=76.7285,
        original_text="gps complaint", audio_path=None, client=client,
    )
    row = client.tables["tickets"][-1]
    assert row["district"] == "Rajgarh" and row["location_precision"] == "exact"


def test_no_gps_and_no_notes_adds_no_location_columns():
    assert ticketing._location_columns({"issue_type": "x"}, "location", None, None, None) == {}


def test_intake_notes_district_wins_for_the_column_too():
    cols = ticketing._location_columns(
        {"_intake": {"location_details": {"district": "Sagar", "tehsil": "Rahatgarh"}}, "location": "Kiloda"}, "location", 24.0, 76.7, "Rajgarh"
    )
    assert cols["district"] == "Sagar" and cols["tehsil"] == "Rahatgarh" and cols["location_precision"] == "exact"
