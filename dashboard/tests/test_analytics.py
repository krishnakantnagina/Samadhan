import pandas as pd

from dashboard.analytics import ageing, daily_received_resolved, daily_trend, department_summary, totals

NOW = pd.Timestamp("2026-10-01T12:00:00Z")


def _frame(rows):
    return pd.DataFrame(rows, columns=["department", "status", "created_at", "updated_at"])


def _ago(days):
    return (NOW - pd.Timedelta(days=days)).isoformat()


ROWS = [
    ("Water", "resolved", _ago(10), _ago(8)),      # resolved in 2 days
    ("Water", "new", _ago(30), _ago(30)),          # pending, overdue (30 > 21)
    ("Water", "in_progress", _ago(2), _ago(1)),    # pending, not overdue
    ("Roads", "needs_review", _ago(5), _ago(5)),   # pending, needs review
    ("Roads", "resolved", _ago(4), _ago(3)),       # resolved in 1 day
]


def test_department_summary_counts():
    s = department_summary(_frame(ROWS), NOW).set_index("department")
    assert s.loc["Water", ["received", "resolved", "pending", "overdue"]].tolist() == [3, 1, 2, 1]
    assert s.loc["Roads", ["received", "resolved", "pending", "overdue", "needs_review"]].tolist() == [2, 1, 1, 0, 1]
    assert s.loc["Water", "resolution_rate"] == 33.3
    assert s.loc["Water", "avg_days_to_resolve"] == 2.0
    assert s.loc["Roads", "avg_days_to_resolve"] == 1.0


def test_sla_days_is_adjustable():
    s = department_summary(_frame(ROWS), NOW, sla_days=3).set_index("department")
    assert s.loc["Roads", "overdue"] == 1  # 5 days old, pending
    assert s.loc["Water", "overdue"] == 1  # the 2-day-old ticket is not overdue; the 30-day one is


def test_most_overdue_department_sorts_first():
    assert department_summary(_frame(ROWS), NOW)["department"].tolist()[0] == "Water"


def test_totals():
    t = totals(department_summary(_frame(ROWS), NOW))
    assert t == {"received": 5, "resolved": 2, "pending": 3, "overdue": 1, "resolution_rate": 40.0}


def test_ageing_buckets_count_only_pending():
    a = ageing(_frame(ROWS), NOW).set_index("age")["tickets"].to_dict()
    assert a == {"0-3 days": 1, "4-7 days": 1, "8-15 days": 0, "16+ days": 1}


def test_daily_trend_is_zero_filled_and_right_length():
    t = daily_trend(_frame(ROWS), NOW, days=30)
    assert len(t) == 30
    assert int(t["received"].sum()) == 4  # the 30-day-old ticket falls just outside the window
    assert t.index[-1] == NOW.normalize()


def test_daily_received_resolved_totals_and_dates():
    rr = daily_received_resolved(_frame(ROWS), NOW)
    assert list(rr.columns) == ["received", "resolved"]
    assert int(rr["received"].sum()) == 4  # the 30-day-old ticket falls just outside the window
    assert int(rr["resolved"].sum()) == 2  # two resolved tickets, dated by their updated_at
    assert int(rr.loc[pd.Timestamp("2026-09-23", tz="UTC"), "resolved"]) == 1  # Water resolved 8 days ago
    assert int(rr.loc[pd.Timestamp("2026-09-28", tz="UTC"), "resolved"]) == 1  # Roads resolved 3 days ago


def test_empty_frames_do_not_crash():
    empty = _frame([])
    assert department_summary(empty, NOW).empty
    assert ageing(empty, NOW)["tickets"].sum() == 0
    assert daily_trend(empty, NOW)["received"].sum() == 0
    rr = daily_received_resolved(empty, NOW)
    assert len(rr) == 30 and int(rr["received"].sum()) == 0 and int(rr["resolved"].sum()) == 0


def test_mixed_timestamp_formats_from_the_live_database_parse():
    """Regression: live rows mix '...T10:05:00+00:00' and '...T10:05:00.123456+00:00'; one inferred format used to crash the Overview."""
    rows = [("Water", "new", "2026-09-28T10:05:00+00:00", "2026-09-28T10:05:00+00:00"),
            ("Water", "resolved", "2026-09-29T08:30:15.123456+00:00", "2026-09-29T09:30:15.654321+00:00")]
    df = _frame(rows)
    assert department_summary(df, NOW).loc[0, "received"] == 2
    assert int(ageing(df, NOW)["tickets"].sum()) == 1
    assert int(daily_trend(df, NOW)["received"].sum()) == 2
