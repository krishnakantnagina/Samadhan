from datetime import UTC, datetime

import pandas as pd
import pytest

from dashboard.analytics import department_summary
from dashboard.cm import area, demo_data
from dashboard.cm.departments import ALL_DEPARTMENTS, LIVE_MAP

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
NOW_TS = pd.Timestamp(NOW)
DISTRICTS = [{"name": n, "division": d, "population_2011": p} for n, d, p in
             [("Bhopal", "Bhopal", 2371061), ("Sagar", "Sagar", 2378295), ("Rewa", "Rewa", 2363744), ("Chhatarpur", "Sagar", 1762375),
              ("Dindori", "Jabalpur", 704218), ("Indore", "Indore", 3276697), ("Shivpuri", "Gwalior", 1725818)]]
NAMES = {d[0]: d[1] for d in ALL_DEPARTMENTS}


def demo(n=360, seed=2026):
    return demo_data.generate(DISTRICTS, NAMES, n=n, seed=seed, now=NOW)


# --- demo data ---------------------------------------------------------------------------------------------------

def test_demo_data_size_and_reproducibility():
    a, b = demo(), demo()
    assert 300 <= len(a) <= 400
    pd.testing.assert_frame_equal(a, b)  # same seed -> same data
    assert not a.equals(demo(seed=7))


def test_demo_rows_are_clearly_labelled_and_valid():
    df = demo()
    assert df["is_demo"].all() and df["complaint_id"].str.startswith("DEMO-").all() and df["complaint_id"].is_unique
    assert set(df["status"]) <= {"new", "in_progress", "resolved", "needs_review"}
    assert set(df["district"]) <= {d["name"] for d in DISTRICTS}
    assert set(df["location_quality"]) <= {"exact", "village", "district", "unknown"}
    created, updated = pd.to_datetime(df["created_at"], format="ISO8601"), pd.to_datetime(df["updated_at"], format="ISO8601")
    assert (updated >= created).all() and (updated <= NOW).all() and (created <= NOW).all()
    assert (NOW - created.min()).days <= 92


def test_demo_uses_samadhan_department_names_for_live_departments_so_role_scoping_works():
    deps = set(demo()["department"])
    assert set(LIVE_MAP) & deps  # live departments appear with their Samadhan names, e.g. "Jal Vibhag"
    assert "Jal Vibhag" in deps and "Bijli Vibhag" in deps


def test_demo_has_a_realistic_spread_and_planted_hotspots_are_found():
    df = demo(n=360)
    assert len(df) == 360 and df["status"].nunique() == 4 and df["department"].nunique() >= 8
    assert 0.35 < (df["status"] == "resolved").mean() < 0.85
    found = area.hotspots(df, NOW_TS, window_days=30, min_count=4)
    pairs = set(zip(found["district"], found["issue"], strict=True))
    assert {("Sagar", "Handpump not working"), ("Rewa", "Power cut for days"), ("Chhatarpur", "MGNREGA wages pending")} <= pairs


def test_generate_refuses_without_districts():
    with pytest.raises(ValueError):
        demo_data.generate([], NAMES)


# --- area analysis -----------------------------------------------------------------------------------------------

def frame(rows):
    return pd.DataFrame(rows, columns=["district", "status", "department", "issue", "created_at", "updated_at", "location_quality"])


def ago(d):
    return (NOW - pd.Timedelta(days=d)).isoformat()


def test_district_summary_counts_rate_and_overdue():
    rows = [("Sagar", "new", "Water", "a", ago(30), ago(30), "exact"), ("Sagar", "resolved", "Water", "a", ago(10), ago(8), "village"),
            ("Rewa", "in_progress", "Power", "b", ago(2), ago(1), "unknown")]
    s = area.district_summary(frame(rows), pd.DataFrame(DISTRICTS), NOW_TS).set_index("district")
    assert s.loc["Sagar", ["received", "resolved", "pending", "overdue"]].tolist() == [2, 1, 1, 1]
    assert s.loc["Sagar", "per_100k"] == round(2 / 2378295 * 100_000, 2)
    assert s.loc["Sagar", "located_pct"] == 100 and s.loc["Rewa", "located_pct"] == 0
    assert area.district_summary(frame(rows), pd.DataFrame(DISTRICTS), NOW_TS).iloc[0]["district"] == "Sagar"  # most overdue first


def test_division_rollup_adds_districts_up():
    rows = [("Sagar", "new", "W", "a", ago(3), ago(3), "exact"), ("Chhatarpur", "new", "W", "a", ago(3), ago(3), "exact")]
    d = area.division_summary(area.district_summary(frame(rows), pd.DataFrame(DISTRICTS), NOW_TS))
    assert d.loc[d["division"] == "Sagar", "received"].iloc[0] == 2


def test_hotspot_rule_new_and_growing_but_not_steady_or_small():
    rows = ([("Sagar", "new", "W", "Handpump", ago(d), ago(d), "exact") for d in (1, 2, 3, 4, 5)]              # 5 recent, 0 before: new
            + [("Rewa", "new", "P", "Power cut", ago(d), ago(d), "exact") for d in (1, 2, 3, 4)]                # 4 recent...
            + [("Rewa", "new", "P", "Power cut", ago(d), ago(d), "exact") for d in (35, 36, 37, 38)]           # ...4 before: steady, not a hotspot
            + [("Indore", "new", "S", "Garbage", ago(d), ago(d), "exact") for d in (1, 2)])                    # below min_count
    hs = area.hotspots(frame(rows), NOW_TS)
    assert list(zip(hs["district"], hs["issue"], hs["change"], strict=True)) == [("Sagar", "Handpump", "new")]


def test_heat_table_and_location_mix_and_empty_inputs():
    rows = [("Sagar", "new", "Water", "a", ago(1), ago(1), "exact"), ("Sagar", "new", "Power", "b", ago(1), ago(1), "village"), ("Rewa", "new", "Water", "a", ago(1), ago(1), "unknown")]
    ht = area.heat_table(frame(rows))
    assert ht.loc["Sagar", "Water"] == 1 and ht.shape == (2, 2)
    assert area.location_mix(frame(rows))["tickets"].tolist() == [1, 1, 0, 1]
    empty = frame([])
    assert area.district_summary(empty, pd.DataFrame(DISTRICTS), NOW_TS).empty and area.heat_table(empty).empty and area.hotspots(empty, NOW_TS).empty


def test_demo_data_works_with_the_existing_department_analytics():
    s = department_summary(demo(), NOW_TS)
    assert s["received"].sum() == 360 and s["resolved"].sum() > 0
