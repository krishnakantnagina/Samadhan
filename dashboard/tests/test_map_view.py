"""S24 map (T30): pure helpers + the folium map, no Streamlit and no network."""

from dashboard.map_view import (
    MP_CENTER,
    DEFAULT_ZOOM,
    STATE_ZOOM,
    SINGLE_PIN_ZOOM,
    build_map,
    center_and_zoom,
    issue_label,
    legend_markdown,
    popup_html,
    split_points,
    status_style,
)
from dashboard.tickets import MAP_COLUMNS


def ticket(cid="SMD-0001", status="new", lat=None, lng=None, **overrides):
    row = {
        "complaint_id": cid,
        "status": status,
        "department": "Jal Vibhag",
        "fields": {"issue_type": "no_supply", "location": "Misrod"},
        "lat": lat,
        "lng": lng,
        "created_at": "2026-09-29T06:49:08.5+00:00",
        "offices": {"office_name": "Ward मिसरोद Office"},
    }
    row.update(overrides)
    return row


def test_split_points_keeps_only_exact_gps_on_the_map():
    rows = [ticket("SMD-0001"), ticket("SMD-0002", lat=23.2, lng=77.4), ticket("SMD-0003", lat=23.3)]
    with_gps, without = split_points(rows)

    assert [r["complaint_id"] for r in with_gps] == ["SMD-0002"]
    # a half-set coordinate is not "exact GPS": it goes to the honest without-GPS list
    assert [r["complaint_id"] for r in without] == ["SMD-0001", "SMD-0003"]


def test_zero_is_a_valid_coordinate():
    with_gps, _ = split_points([ticket(lat=0.0, lng=0.0)])
    assert len(with_gps) == 1


def test_status_style_has_a_name_for_every_status_and_a_fallback():
    for status in ("new", "in_progress", "resolved", "needs_review"):
        color, name = status_style(status)
        assert color.startswith("#") and name
    assert status_style("weird")[1] == "Unknown"


def test_legend_names_every_status():
    text = legend_markdown()
    for name in ("New", "In progress", "Resolved", "Needs review"):
        assert name in text


def test_popup_contains_the_facts_and_is_html_escaped():
    row = ticket(fields={"issue_type": "<script>alert(1)</script>"}, offices={"office_name": "A&B"})
    html = popup_html(row)

    assert "SMD-0001" in html and "Status: New" in html and "A&amp;B" in html
    assert "<script>" not in html
    assert "2026-09-29 06:49" in html


def test_issue_label_uses_english_label_and_survives_missing_fields():
    assert issue_label(ticket()) == "No water supply"
    assert issue_label(ticket(fields=None)) == "-"


def test_center_and_zoom_cases():
    assert center_and_zoom([]) == (MP_CENTER, STATE_ZOOM)
    assert center_and_zoom([{"lat": 23.2, "lng": 77.4}]) == ((23.2, 77.4), SINGLE_PIN_ZOOM)
    (lat, lng), zoom = center_and_zoom([{"lat": 23.0, "lng": 77.0}, {"lat": 24.0, "lng": 78.0}])
    assert (lat, lng, zoom) == (23.5, 77.5, DEFAULT_ZOOM)


def test_build_map_draws_one_marker_per_point_coloured_by_status():
    points = [
        ticket("SMD-0005", "resolved", 23.2493, 77.423),
        ticket("SMD-0011", "in_progress", 23.2156, 77.4384),
    ]
    html = build_map(points).get_root().render()

    assert html.count("circleMarker") >= 2 or html.count("L.circleMarker") == 2
    assert "SMD-0005" in html and "SMD-0011" in html
    assert status_style("resolved")[0] in html and status_style("in_progress")[0] in html


def test_build_map_with_no_points_is_a_plain_bhopal_map():
    html = build_map([]).get_root().render()
    assert "L.circleMarker" not in html


def test_map_query_never_selects_citizen_only_columns():
    """S24 section 4: lat/lng yes, but never original_text / audio_path / session_id."""
    for forbidden in ("original_text", "audio_path", "session_id", "*"):
        assert forbidden not in MAP_COLUMNS
    assert "lat" in MAP_COLUMNS and "lng" in MAP_COLUMNS
