"""Overview analytics: per-department KPIs, ageing buckets, daily trend.

Pure pandas over the ticket frame the app already loads (`_cached_tickets`); no DB access, so it is
cheap to test. "Pending" = any status other than `resolved`. "Overdue" = pending for more than
`sla_days`. The default 21 days is CPGRAMS's national resolution time (pgportal.gov.in process flow);
MP's Lok Seva Guarantee deadlines differ per service, so the dashboard lets the officer change it.
"""

import pandas as pd

DEFAULT_SLA_DAYS = 21
AGEING_BUCKETS = [("0-3 days", 0, 3), ("4-7 days", 4, 7), ("8-15 days", 8, 15), ("16+ days", 16, None)]


def _prepare(df: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    out = df.copy()
    out["created_at"] = pd.to_datetime(out["created_at"], utc=True, format="ISO8601")  # live rows mix with/without fractional seconds
    out["updated_at"] = pd.to_datetime(out["updated_at"], utc=True, format="ISO8601")
    out["pending"] = out["status"] != "resolved"
    out["age_days"] = (now - out["created_at"]).dt.total_seconds() / 86400
    return out


def department_summary(df: pd.DataFrame, now: pd.Timestamp, sla_days: int = DEFAULT_SLA_DAYS) -> pd.DataFrame:
    """One row per department: received, resolved, pending, overdue, resolution rate, avg days to resolve.

    Time to resolve is updated_at - created_at for resolved tickets (the status change is the last
    update); it is approximate if an officer edits a ticket again after resolving it."""
    if df.empty:
        return pd.DataFrame(
            columns=["department", "received", "resolved", "pending", "overdue", "needs_review",
                     "resolution_rate", "avg_days_to_resolve"]
        )
    t = _prepare(df, now)
    t["overdue"] = t["pending"] & (t["age_days"] > sla_days)
    t["days_to_resolve"] = ((t["updated_at"] - t["created_at"]).dt.total_seconds() / 86400).where(~t["pending"])
    grouped = t.groupby("department")
    summary = pd.DataFrame(
        {
            "received": grouped.size(),
            "resolved": grouped["pending"].apply(lambda s: int((~s).sum())),
            "pending": grouped["pending"].sum().astype(int),
            "overdue": grouped["overdue"].sum().astype(int),
            "needs_review": grouped["status"].apply(lambda s: int((s == "needs_review").sum())),
            "avg_days_to_resolve": grouped["days_to_resolve"].mean().round(1),
        }
    )
    summary["resolution_rate"] = (summary["resolved"] / summary["received"] * 100).round(1)
    cols = ["received", "resolved", "pending", "overdue", "needs_review", "resolution_rate", "avg_days_to_resolve"]
    return summary[cols].reset_index().sort_values(["overdue", "pending"], ascending=False, ignore_index=True)


def totals(summary: pd.DataFrame) -> dict[str, float]:
    """State-level KPI tiles from a department_summary frame."""
    received = int(summary["received"].sum())
    resolved = int(summary["resolved"].sum())
    return {
        "received": received,
        "resolved": resolved,
        "pending": int(summary["pending"].sum()),
        "overdue": int(summary["overdue"].sum()),
        "resolution_rate": round(resolved / received * 100, 1) if received else 0.0,
    }


def ageing(df: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """Pending tickets per age bucket (CPGRAMS-style age-wise pendency)."""
    t = _prepare(df, now) if not df.empty else df
    pending_ages = t.loc[t["pending"], "age_days"] if not df.empty else pd.Series(dtype=float)
    rows = []
    for label, low, high in AGEING_BUCKETS:
        mask = pending_ages >= low
        if high is not None:
            mask &= pending_ages < high + 1
        rows.append({"age": label, "tickets": int(mask.sum())})
    return pd.DataFrame(rows)


def daily_trend(df: pd.DataFrame, now: pd.Timestamp, days: int = 30) -> pd.DataFrame:
    """Tickets received per day for the last `days` days (zero-filled), indexed by date."""
    index = pd.date_range(end=now.normalize(), periods=days, freq="D", tz="UTC")
    if df.empty:
        return pd.DataFrame({"received": 0}, index=index)
    created = pd.to_datetime(df["created_at"], utc=True, format="ISO8601").dt.normalize()
    counts = created.value_counts().reindex(index, fill_value=0).sort_index()
    return counts.rename("received").to_frame()
