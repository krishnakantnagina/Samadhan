"""CM-centre area analysis: where are complaints concentrated, slow, or rising? Pure pandas over a ticket frame that has `district`.

Needs columns: status, department, created_at, updated_at, district (+ division, issue, location_quality when present).
Population comes from the registry (2011 census, via mpinfo.org). A rate per 100k people is shown next to raw counts because big districts always
have more complaints; it still reflects who can reach the system (phone/internet/awareness), not only where problems are. Say so wherever it is shown.
"""

import pandas as pd

from dashboard.analytics import DEFAULT_SLA_DAYS, _prepare


def district_summary(df: pd.DataFrame, districts: pd.DataFrame, now: pd.Timestamp, sla_days: int = DEFAULT_SLA_DAYS) -> pd.DataFrame:
    """One row per district that has tickets: counts, pending/overdue, average days to resolve, tickets per 100k people, share with an exact or village location."""
    cols = ["district", "division", "received", "resolved", "pending", "overdue", "resolution_rate", "avg_days_to_resolve", "per_100k", "located_pct"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    t = _prepare(df, now)
    t["overdue"] = t["pending"] & (t["age_days"] > sla_days)
    t["days"] = ((t["updated_at"] - t["created_at"]).dt.total_seconds() / 86400).where(~t["pending"])
    t["located"] = t["location_quality"].isin(["exact", "village"]) if "location_quality" in t else False
    g = t.groupby("district")
    out = pd.DataFrame({
        "received": g.size(), "resolved": g["pending"].apply(lambda s: int((~s).sum())), "pending": g["pending"].sum().astype(int),
        "overdue": g["overdue"].sum().astype(int), "avg_days_to_resolve": g["days"].mean().round(1), "located_pct": (g["located"].mean() * 100).round(0),
    }).reset_index()
    out["resolution_rate"] = (out["resolved"] / out["received"] * 100).round(1)
    meta = districts[["name", "division", "population_2011"]].rename(columns={"name": "district"})
    out = out.merge(meta, how="left", on="district")
    out["per_100k"] = (out["received"] / out["population_2011"] * 100_000).round(2)
    return out[cols].sort_values(["overdue", "received"], ascending=False, ignore_index=True)


def division_summary(dist: pd.DataFrame) -> pd.DataFrame:
    """Roll the district summary up to divisions (the commissioner level)."""
    if dist.empty:
        return dist
    g = dist.groupby("division", dropna=False)
    out = g[["received", "resolved", "pending", "overdue"]].sum().reset_index()
    out["resolution_rate"] = (out["resolved"] / out["received"] * 100).round(1)
    return out.sort_values("received", ascending=False, ignore_index=True)


def heat_table(df: pd.DataFrame, rows: str = "district", cols: str = "department", top_rows: int = 12, top_cols: int = 8) -> pd.DataFrame:
    """Count matrix of the busiest `rows` by the busiest `cols` (e.g. districts x departments), for a colour-scaled table."""
    if df.empty:
        return pd.DataFrame()
    r = df[rows].value_counts().head(top_rows).index
    c = df[cols].value_counts().head(top_cols).index
    sub = df[df[rows].isin(r) & df[cols].isin(c)]
    return pd.crosstab(sub[rows], sub[cols]).reindex(index=r, columns=c, fill_value=0)


def hotspots(df: pd.DataFrame, now: pd.Timestamp, window_days: int = 30, min_count: int = 4, growth: float = 1.5) -> pd.DataFrame:
    """(district, issue) pairs with at least `min_count` complaints in the last window that are new or grew by `growth`x versus the window before.
    A simple, explainable rule on purpose: an officer can check each row by eye."""
    cols = ["district", "issue", "last_window", "previous_window", "change", "pending_now"]
    if df.empty or "issue" not in df:
        return pd.DataFrame(columns=cols)
    t = _prepare(df, now)
    recent = t[t["age_days"] <= window_days]
    before = t[(t["age_days"] > window_days) & (t["age_days"] <= 2 * window_days)]
    a = recent.groupby(["district", "issue"]).size().rename("last_window")
    b = before.groupby(["district", "issue"]).size().rename("previous_window")
    p = recent[recent["pending"]].groupby(["district", "issue"]).size().rename("pending_now")
    out = pd.concat([a, b, p], axis=1).fillna(0).astype(int).reset_index()
    out = out[(out["last_window"] >= min_count) & ((out["previous_window"] == 0) | (out["last_window"] >= growth * out["previous_window"]))]
    out["change"] = out.apply(lambda r: "new" if r["previous_window"] == 0 else f"x{r['last_window'] / r['previous_window']:.1f}", axis=1)
    return out[cols].sort_values(["last_window", "pending_now"], ascending=False, ignore_index=True)


def location_mix(df: pd.DataFrame) -> pd.DataFrame:
    """How precisely tickets say where they are: exact / village / district / unknown."""
    if df.empty or "location_quality" not in df:
        return pd.DataFrame({"tickets": []})
    order = ["exact", "village", "district", "unknown"]
    return df["location_quality"].value_counts().reindex(order, fill_value=0).rename("tickets").to_frame()
