"""S24 -- officer map (T30). Spec: docs/specs/S24-dashboard-map.md.

Pure helpers (split, colour, popup, centre/zoom) are separate from folium/Streamlit so they can be unit
tested. Only exact GPS is ever pinned; a ticket without GPS is counted and listed, never faked onto the
map (S24 D-S24-1, S09).
"""

from html import escape
from typing import Any

import folium

from dashboard.labels import ISSUE_TYPE_LABELS_EN

MP_CENTER = (23.4733, 77.9470)  # centre of Madhya Pradesh
DEFAULT_ZOOM = 11
STATE_ZOOM = 6
SINGLE_PIN_ZOOM = 15

# Colour + name per status. The legend and popups always print the name: colour is never the only cue.
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "new": ("#2563eb", "New"),
    "in_progress": ("#d97706", "In progress"),
    "resolved": ("#16a34a", "Resolved"),
    "needs_review": ("#dc2626", "Needs review"),
}
UNKNOWN_STYLE = ("#64748b", "Unknown")


def status_style(status: str) -> tuple[str, str]:
    return STATUS_STYLE.get(status, UNKNOWN_STYLE)


def has_gps(row: dict[str, Any]) -> bool:
    return row.get("lat") is not None and row.get("lng") is not None


def split_points(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(tickets with exact GPS, tickets without). Order preserved."""
    with_gps = [r for r in rows if has_gps(r)]
    without = [r for r in rows if not has_gps(r)]
    return with_gps, without


def issue_label(row: dict[str, Any]) -> str:
    fields = row.get("fields") or {}
    issue = fields.get("issue_type")
    if issue:
        return ISSUE_TYPE_LABELS_EN.get(issue, str(issue))
    description = fields.get("description")  # S28 general triage tickets
    return str(description)[:60] if description else "-"


def office_name(row: dict[str, Any]) -> str:
    return (row.get("offices") or {}).get("office_name") or "-"


def popup_html(row: dict[str, Any]) -> str:
    """Escaped: field values come from citizens, never inject them raw into HTML."""
    _, status_name = status_style(row["status"])
    lines = [
        f"<b>{escape(row['complaint_id'])}</b>",
        f"Status: {escape(status_name)}",
        f"Issue: {escape(issue_label(row))}",
        f"Office: {escape(office_name(row))}",
        f"Created: {escape(str(row.get('created_at', '-'))[:16].replace('T', ' '))}",
    ]
    return "<br>".join(lines)


def center_and_zoom(points: list[dict[str, Any]]) -> tuple[tuple[float, float], int]:
    """No pins -> the whole state; one pin -> that pin, close; 2+ -> the mean (build_map
    then also fits the bounds)."""
    if not points:
        return MP_CENTER, STATE_ZOOM
    lat = sum(p["lat"] for p in points) / len(points)
    lng = sum(p["lng"] for p in points) / len(points)
    return (lat, lng), SINGLE_PIN_ZOOM if len(points) == 1 else DEFAULT_ZOOM


def build_map(points: list[dict[str, Any]]) -> folium.Map:
    center, zoom = center_and_zoom(points)
    fmap = folium.Map(location=center, zoom_start=zoom, control_scale=True)
    for p in points:
        color, status_name = status_style(p["status"])
        folium.CircleMarker(
            location=(p["lat"], p["lng"]),
            radius=9,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            tooltip=f"{p['complaint_id']} · {status_name}",
            popup=folium.Popup(popup_html(p), max_width=260),
        ).add_to(fmap)
    if len(points) >= 2:
        lats = [p["lat"] for p in points]
        lngs = [p["lng"] for p in points]
        fmap.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], padding=(30, 30))
    return fmap


def legend_markdown() -> str:
    """Text legend (name next to a coloured dot) shown above the map."""
    return " &nbsp;·&nbsp; ".join(
        f'<span style="color:{color}">●</span> {name}' for color, name in STATUS_STYLE.values()
    )
