"""Small UI helpers shared by every table in the CM-office system.

Column headers are drawn on a canvas by Streamlit's grid, so CSS cannot change their case; instead every table goes through `table()`, which shows
the column names in CAPITALS (underscores become spaces). Border and header colours come from the theme in .streamlit/config.toml.
"""

import pandas as pd
import streamlit as st


def label(name) -> str:
    return str(name).replace("_", " ").upper()


def sparkline_svg(values, color: str = "#0b5cab", w: int = 68, h: int = 26, pad: int = 3) -> str:
    """A tiny inline SVG sparkline (filled area + line + end dot) from a list of numbers. Returns '' for <2 points."""
    nums = [float(v) for v in (values or [])]
    if len(nums) < 2:
        return ""
    lo, hi = min(nums), max(nums)
    span = (hi - lo) or 1.0
    n = len(nums)
    pts = [((i / (n - 1)) * w, pad + (1 - (v - lo) / span) * (h - 2 * pad)) for i, v in enumerate(nums)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    return (
        f'<svg class="cm-spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
        f'<polygon points="0,{h} {line} {w},{h}" fill="var(--chip)"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.4" fill="{color}"/></svg>'
    )


def kpi_cards(cards: list[dict]) -> str:
    """HTML for a responsive row of KPI cards. Each card: {label, value, icon?, spark?: list, color?, delta?}.
    Values and labels are app-controlled copy, never citizen text. Render with st.markdown(..., unsafe_allow_html=True)."""
    out = ['<div class="cm-kpis">']
    for c in cards:
        icon = f'<span class="ic">{c.get("icon", "")}</span>' if c.get("icon") else ""
        spark = sparkline_svg(c.get("spark"), c.get("color", "#0b5cab")) if c.get("spark") else ""
        delta = f'<span class="d">{c["delta"]}</span>' if c.get("delta") else "<span></span>"
        out.append(
            '<div class="cm-kpi">'
            f'<div class="r1">{icon}<span class="lab">{c["label"]}</span></div>'
            f'<div class="val">{c["value"]}</div>'
            f'<div class="meta">{delta}{spark}</div>'
            "</div>"
        )
    out.append("</div>")
    return "".join(out)


def table(data, **kwargs):
    """st.dataframe with capitalised column names, full width, and the row index hidden when it is just 0..n. Accepts a DataFrame or a Styler."""
    kwargs.setdefault("width", "stretch")
    if isinstance(data, pd.DataFrame):
        shown = data.rename(columns=label)
        kwargs.setdefault("hide_index", isinstance(data.index, pd.RangeIndex))
    elif hasattr(data, "format_index"):  # pandas Styler: change the displayed header only
        shown = data.format_index(label, axis=1)
        kwargs.setdefault("hide_index", isinstance(data.data.index, pd.RangeIndex))
    else:
        shown = data
    return st.dataframe(shown, **kwargs)
