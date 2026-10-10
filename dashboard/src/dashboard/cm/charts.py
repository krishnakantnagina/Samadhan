"""Overview charts and KPI glyphs shared by the CM command centre and the officer dashboard.

Altair in the government blue palette: a received-vs-resolved trend and a pending-by-department donut. The palette has no
categorical hues, so the donut's identity is carried by its legend labels, not colour alone (see the dataviz guidance)."""

import altair as alt
import pandas as pd

from dashboard.analytics import daily_received_resolved
from dashboard.cm import theme

# KPI-card glyphs (stroke uses currentColor so the theme tints them)
ICON_INBOX = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5h16M4 12h16M4 19h10"/></svg>'
ICON_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg>'
ICON_CLOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
ICON_ALERT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.3 3.9 2 18a2 2 0 0 0 1.7 3h16.6A2 2 0 0 0 22 18L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4m0 4h.01"/></svg>'
# one blue->grey family; identity comes from the legend labels, not the hue
DONUT_RAMP = [theme.NAVY, theme.BLUE, theme.SKY, "#7fb2e6", "#9fb3c8", theme.GREY, "#c3d2e3"]


def trend_chart(df: pd.DataFrame, now: pd.Timestamp) -> alt.LayerChart:
    """Received (filled area + line) vs resolved (line) per day for the last 30 days."""
    tr = daily_received_resolved(df, now).reset_index(names="date")
    long = tr.melt("date", var_name="series", value_name="tickets")
    long["series"] = long["series"].map({"received": "Received", "resolved": "Resolved"})
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d %b", labelColor=theme.MUTED, tickColor=theme.GREY_LIGHT, domainColor=theme.GREY_LIGHT, labelFontSize=11))
    y = alt.Y("tickets:Q", title=None, axis=alt.Axis(labelColor=theme.MUTED, gridColor="#e6ecf4", domainOpacity=0, tickOpacity=0, labelFontSize=11))
    scale = alt.Scale(domain=["Received", "Resolved"], range=[theme.BLUE, theme.NAVY])
    area = alt.Chart(long).transform_filter("datum.series == 'Received'").mark_area(opacity=0.12, color=theme.BLUE).encode(x=x, y=y)
    lines = alt.Chart(long).mark_line(strokeWidth=2).encode(
        x=x, y=y,
        color=alt.Color("series:N", scale=scale, legend=alt.Legend(orient="top", title=None, labelColor=theme.INK)),
        tooltip=[alt.Tooltip("date:T", title="Date", format="%d %b"), alt.Tooltip("series:N", title="Series"), alt.Tooltip("tickets:Q", title="Tickets")],
    )
    return (area + lines).properties(height=260).configure_view(stroke=None)


def donut_open_by_dept(summary: pd.DataFrame) -> alt.Chart:
    """Pending tickets by department as a donut; the seventh and beyond fold into 'Other'."""
    d = summary.loc[summary["pending"] > 0, ["department", "pending"]].sort_values("pending", ascending=False).reset_index(drop=True)
    if len(d) > 6:
        other = pd.DataFrame([{"department": "Other", "pending": int(d.iloc[6:]["pending"].sum())}])
        d = pd.concat([d.iloc[:6], other], ignore_index=True)
    return alt.Chart(d).mark_arc(innerRadius=58, stroke="#ffffff", strokeWidth=2).encode(
        theta=alt.Theta("pending:Q", stack=True),
        color=alt.Color("department:N", sort=None, scale=alt.Scale(range=DONUT_RAMP), legend=alt.Legend(orient="right", title=None, labelColor=theme.INK)),
        tooltip=[alt.Tooltip("department:N", title="Department"), alt.Tooltip("pending:Q", title="Pending")],
    ).properties(height=260).configure_view(stroke=None)
