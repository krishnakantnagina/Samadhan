"""Blue / white / grey government theme for the CM-office system.

Government look: deep navy and blue lead, light-grey page, white panels. Only blue, white and grey are used (no orange, green or red); charts sit on white panels
in blues and greys. `inject()` adds the CSS once per page run; charts use CHART_COLOURS.
"""

import streamlit as st

NAVY = "#0b2e59"
BLUE = "#0b5cab"
SKY = "#3b8fd9"
BRIGHT = "#008eff"
LIGHT = "#e3eefa"
LIGHTER = "#eef2f7"  # page background: cool light grey
GREY = "#6b7787"
GREY_LIGHT = "#dfe6ef"  # hairline / card border
ORANGE = BLUE  # kept as names so old imports work; the palette is blue / white / grey only
DEEP_ORANGE = NAVY
ALERT = "#44546a"  # dark slate for "bad" values
INK = "#0b1f33"
MUTED = "#12304d"
CHART_COLOURS = [BLUE, GREY, SKY, NAVY, "#9fb3c8", ALERT]

PANEL = "#ffffff"
TINT = "#f3f7fc"  # row / soft hover tint
CHIP = "#e7effa"  # soft blue chip
# Soft layered depth -- the "little 2D" lift on cards and panels.
SHADOW = "0 1px 2px rgba(11,46,89,.06), 0 6px 18px rgba(11,46,89,.08)"
SHADOW_LIFT = "0 2px 4px rgba(11,46,89,.10), 0 14px 30px rgba(11,46,89,.16)"
RADIUS = "12px"

CSS = f"""
<style>
:root {{ --navy:{NAVY}; --blue:{BLUE}; --sky:{SKY}; --bright:{BRIGHT}; --light:{LIGHT}; --orange:{ORANGE}; --deep-orange:{DEEP_ORANGE}; --ink:{INK};
  --panel:{PANEL}; --line:{GREY_LIGHT}; --tint:{TINT}; --chip:{CHIP}; --muted:{MUTED}; --radius:{RADIUS}; --shadow:{SHADOW}; --shadow-lift:{SHADOW_LIFT}; }}
[data-testid="stAppViewContainer"] {{ background:{LIGHTER}; color:{INK}; }}
[data-testid="stHeader"] {{ background:{LIGHTER}; border-bottom:0; box-shadow:none; }}
.stAppDeployButton, [data-testid="stAppDeployButton"] {{ display:none; }}
.cm-card .nm {{ display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-weight:700; color:{NAVY}; min-height:2.9em; }}
[data-testid="stSidebar"] {{ background:linear-gradient(180deg,{NAVY} 0%,#12427f 100%); }}
[data-testid="stSidebar"] * {{ color:#eaf4ff !important; }}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {{ color:{INK} !important; background:#fff !important; }}
/* crafted sidebar: brand block, user card, rounded nav pills */
[data-testid="stSidebar"] .cm-side-brand {{ display:flex; align-items:center; gap:11px; padding:2px 6px 14px; }}
[data-testid="stSidebar"] .cm-side-brand .mark {{ width:40px; height:40px; border-radius:11px; background:rgba(255,255,255,.14); display:grid; place-items:center; font-weight:800; font-size:20px; color:#fff !important; }}
[data-testid="stSidebar"] .cm-side-brand .nm {{ font-weight:800; font-size:15px; color:#fff !important; line-height:1.1; }}
[data-testid="stSidebar"] .cm-side-brand .sub {{ font-size:10px; letter-spacing:1px; color:#bcd6f5 !important; }}
[data-testid="stSidebar"] .cm-side-user {{ display:flex; align-items:center; gap:9px; padding:9px 10px; margin:0 0 10px; border-radius:10px; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.14); }}
[data-testid="stSidebar"] .cm-side-user .av {{ width:30px; height:30px; border-radius:50%; background:rgba(255,255,255,.18); display:grid; place-items:center; font-weight:700; font-size:11px; color:#fff !important; flex:none; }}
[data-testid="stSidebar"] .cm-side-user b {{ display:block; color:#fff !important; font-size:12.5px; font-weight:700; }}
[data-testid="stSidebar"] .cm-side-user span {{ color:#bcd6f5 !important; font-size:11px; }}
[data-testid="stSidebarNav"] a {{ border-radius:9px !important; padding:7px 11px !important; margin:1px 2px !important; border-left:3px solid transparent; }}
[data-testid="stSidebarNav"] a:hover {{ background:rgba(255,255,255,.08) !important; }}
[data-testid="stSidebarNav"] a[aria-current="page"], [data-testid="stSidebarNav"] a[data-testid="stSidebarNavLink"][aria-current="page"] {{ background:rgba(255,255,255,.18) !important; border-left:3px solid #ffffff; }}
h1, h2, h3 {{ color:{NAVY}; letter-spacing:.2px; }}
h1 {{ font-weight:800; }}
h2 {{ font-weight:700; }}
/* KPI tiles: white, rounded, left accent stripe, soft lift */
[data-testid="stMetric"] {{ background:{PANEL}; border:1px solid {GREY_LIGHT}; border-left:4px solid {BLUE}; border-radius:{RADIUS}; padding:.85rem 1rem; box-shadow:{SHADOW}; position:relative; overflow:hidden; }}
[data-testid="stMetricValue"] {{ color:{NAVY}; font-weight:700; font-variant-numeric:tabular-nums; }}
[data-testid="stMetricLabel"] p {{ color:{MUTED}; font-weight:600; letter-spacing:.3px; }}
.stButton > button, .stFormSubmitButton > button {{ background:{BLUE}; color:#fff; border:0; border-radius:9px; font-weight:600; box-shadow:{SHADOW}; }}
.stButton > button:hover, .stFormSubmitButton > button:hover {{ background:{NAVY}; color:#fff; }}
[data-baseweb="tab"][aria-selected="true"] {{ color:{NAVY}; border-bottom:3px solid {BLUE}; }}
/* inputs, selects and text areas: light hairline, sky focus ring */
.stTextInput [data-baseweb="input"], .stNumberInput [data-baseweb="input"], .stTextArea [data-baseweb="textarea"], .stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div, .stDateInput [data-baseweb="input"] {{ border:1px solid {GREY_LIGHT} !important; border-radius:9px !important; background:#ffffff !important; }}
.stTextInput [data-baseweb="input"]:focus-within, .stSelectbox [data-baseweb="select"] > div:focus-within, .stTextArea [data-baseweb="textarea"]:focus-within {{ border-color:{SKY} !important; box-shadow:0 0 0 3px rgba(59,143,217,.18) !important; }}
.stTextInput input, .stNumberInput input, .stTextArea textarea {{ color:{INK} !important; }}
[data-testid="stSidebar"] .stTextInput [data-baseweb="input"], [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div {{ border:1px solid #9fc3e8 !important; }}
/* tables: light frame, rounded, soft shadow; header colours come from .streamlit/config.toml */
[data-testid="stDataFrame"] {{ border:1px solid {GREY_LIGHT}; border-radius:{RADIUS}; background:#ffffff; box-shadow:{SHADOW}; overflow:hidden; }}
/* readable text on the grey page */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *, .stCaption, .stCaption *, [data-testid="stAppViewContainer"] small {{ color:#0b1f33 !important; opacity:1 !important; }}
[data-testid="stAppViewContainer"] label, [data-testid="stAppViewContainer"] [data-testid="stWidgetLabel"] p {{ color:{INK} !important; font-weight:600; }}
[data-baseweb="tab"] {{ color:{INK}; font-weight:600; }}
hr {{ border-color:{GREY} !important; opacity:.25; }}
/* charts: white panel with the same soft depth */
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {{ background:#fff; border:1px solid {GREY_LIGHT}; border-radius:{RADIUS}; padding:.7rem .8rem; box-shadow:{SHADOW}; }}
/* shared components, so every page reads as one crafted system */
[data-baseweb="tab-list"] {{ gap:.25rem; border-bottom:1px solid {GREY_LIGHT}; }}
[data-baseweb="tab"] {{ border-radius:8px 8px 0 0; padding:.45rem .9rem; }}
[data-baseweb="tab"]:hover {{ background:{TINT}; }}
[data-testid="stExpander"] {{ border:1px solid {GREY_LIGHT}; border-radius:{RADIUS}; background:{PANEL}; box-shadow:{SHADOW}; overflow:hidden; }}
[data-testid="stExpander"] summary {{ font-weight:600; color:{NAVY}; }}
[data-testid="stExpander"] summary:hover {{ color:{BLUE}; }}
[data-testid="stAlert"] {{ border-radius:{RADIUS}; border:1px solid {GREY_LIGHT}; box-shadow:{SHADOW}; }}
[data-testid="stNotification"] {{ border-radius:{RADIUS}; box-shadow:{SHADOW}; }}
.stDownloadButton > button, .stButton > button[kind="secondary"] {{ background:{PANEL}; color:{NAVY}; border:1px solid {GREY_LIGHT}; border-radius:9px; font-weight:600; box-shadow:{SHADOW}; }}
.stDownloadButton > button:hover, .stButton > button[kind="secondary"]:hover {{ background:{TINT}; color:{NAVY}; border-color:{BLUE}; }}
/* section headings: a small accent bar so sub-sections look designed on every page */
[data-testid="stAppViewContainer"] h2, [data-testid="stAppViewContainer"] h3 {{ padding-left:.6rem; border-left:3px solid {BLUE}; }}
.cm-hero h1, .cm-topbar .nm {{ padding-left:0; border-left:0; }}
.cm-hero {{ background:linear-gradient(120deg,{NAVY} 0%,{BLUE} 62%,{SKY} 100%); color:#fff; border-radius:{RADIUS}; padding:2rem 2.2rem; position:relative; overflow:hidden; box-shadow:{SHADOW_LIFT}; }}
.cm-hero h1 {{ color:#fff; border:0; font-size:2.6rem; margin:0; }}
.cm-hero .tag {{ color:#cfe0f2; font-weight:600; letter-spacing:1.4px; text-transform:uppercase; font-size:.8rem; }}
.cm-quote {{ font-size:1.25rem; line-height:1.5; margin:1rem 0 .2rem; max-width:46rem; position:relative; z-index:1; }}
.cm-quote-hi {{ color:#cfe6ff; font-size:1.05rem; position:relative; z-index:1; }}
.cm-card {{ background:{PANEL}; border:1px solid {GREY_LIGHT}; border-left:4px solid {NAVY}; border-radius:{RADIUS}; padding:.95rem 1.05rem; height:100%; box-shadow:{SHADOW}; }}
.cm-card b {{ color:{NAVY}; }}
.cm-card small {{ color:{MUTED}; }}
.cm-stat {{ background:rgba(255,255,255,.10); border:0; border-top:3px solid #ffffff; border-radius:10px; padding:.7rem 1rem; text-align:center; position:relative; z-index:1; }}
.cm-stat .n {{ font-size:1.7rem; font-weight:700; color:#fff; font-variant-numeric:tabular-nums; }}
.cm-stat .l {{ font-size:.78rem; color:#cfe6ff; letter-spacing:.4px; }}
.cm-chip {{ display:inline-block; background:{CHIP}; color:{NAVY}; border:1px solid {GREY_LIGHT}; border-radius:999px; padding:.15rem .75rem; margin:.15rem .2rem; font-size:.82rem; font-weight:600; }}
.cm-badge-demo {{ display:inline-block; background:{GREY}; color:#fff; border-radius:999px; padding:.1rem .6rem; font-size:.75rem; font-weight:700; letter-spacing:.6px; }}
.cm-badge-live {{ display:inline-block; background:{BLUE}; color:#fff; border-radius:999px; padding:.1rem .6rem; font-size:.75rem; font-weight:700; letter-spacing:.6px; }}
.cm-hit {{ background:{PANEL}; border:1px solid {GREY_LIGHT}; border-left:3px solid {BLUE}; border-radius:10px; padding:.65rem .9rem; margin:.3rem 0; box-shadow:{SHADOW}; }}
.cm-hit .k {{ color:{BLUE}; font-size:.72rem; font-weight:700; letter-spacing:.8px; text-transform:uppercase; }}
.cm-hit .t {{ color:{NAVY}; font-weight:600; }}
.cm-hit .s {{ color:{MUTED}; font-size:.85rem; }}
/* page spacing: Streamlit's default top gap is large */
.block-container {{ padding-top:3.1rem !important; padding-bottom:2rem !important; max-width:1240px; }}
[data-testid="stHeader"] {{ height:2.4rem; }}
.cm-topbar {{ display:flex; align-items:center; gap:.7rem; padding:.2rem 0 .1rem; }}
.cm-topbar .mark {{ width:40px; height:40px; border-radius:11px; background:linear-gradient(145deg,{NAVY},{BLUE}); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1.25rem; box-shadow:{SHADOW}; }}
.cm-topbar .nm {{ font-weight:800; color:{NAVY}; font-size:1.15rem; line-height:1.1; }}
.cm-topbar .sub {{ color:{MUTED}; font-size:.78rem; letter-spacing:.4px; }}
.cm-stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:.7rem; margin-top:1.1rem; }}
.cm-hero {{ margin-top:.5rem; }}
.cm-steps {{ display:grid; grid-template-columns:repeat(3,1fr); gap:.8rem; margin:1rem 0 .4rem; }}
.cm-step {{ background:{PANEL}; border:1px solid {GREY_LIGHT}; border-top:3px solid {NAVY}; border-radius:{RADIUS}; padding:.95rem 1.05rem; box-shadow:{SHADOW}; }}
.cm-step .no {{ color:{BLUE}; font-weight:800; font-size:.8rem; letter-spacing:1px; }}
.cm-step b {{ display:block; color:{NAVY}; margin:.15rem 0 .25rem; }}
.cm-step small {{ color:{MUTED}; }}
.cm-facts {{ display:flex; flex-wrap:wrap; gap:.4rem; margin-top:.9rem; position:relative; z-index:1; }}
.cm-facts span {{ background:rgba(255,255,255,.14); border-top:2px solid #fff; border-radius:8px; padding:.25rem .65rem; font-size:.8rem; color:#fff; }}
/* KPI cards: icon badge, big tabular number, delta + sparkline (home / command centre) */
.cm-kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(158px,1fr)); gap:.8rem; margin:.3rem 0 1.1rem; }}
.cm-kpi {{ background:{PANEL}; border:1px solid {GREY_LIGHT}; border-radius:{RADIUS}; padding:.85rem 1rem; box-shadow:{SHADOW}; }}
.cm-kpi .r1 {{ display:flex; align-items:center; gap:.55rem; }}
.cm-kpi .ic {{ width:30px; height:30px; border-radius:9px; background:{CHIP}; color:{BLUE}; display:grid; place-items:center; flex:none; }}
.cm-kpi .ic svg {{ width:17px; height:17px; }}
.cm-kpi .lab {{ font-size:.76rem; color:{MUTED}; font-weight:600; }}
.cm-kpi .val {{ font-size:1.7rem; font-weight:700; color:{NAVY}; margin-top:.5rem; line-height:1; font-variant-numeric:tabular-nums; }}
.cm-kpi .meta {{ display:flex; align-items:center; justify-content:space-between; gap:.5rem; margin-top:.5rem; min-height:26px; }}
.cm-kpi .meta .d {{ font-size:.72rem; font-weight:700; color:{BLUE}; }}
.cm-kpi .cm-spark {{ width:66px; height:26px; }}
/* motion: a gentle rise on the home page, a lift on every ticket-like card (switched off for people who prefer reduced motion) */
@keyframes cm-rise {{ from {{ opacity:0; transform:translateY(16px); }} to {{ opacity:1; transform:none; }} }}
@keyframes cm-drift {{ 0% {{ background-position:0% 50%; }} 50% {{ background-position:100% 50%; }} 100% {{ background-position:0% 50%; }} }}
.cm-topbar {{ animation:cm-rise .45s ease both; }}
.cm-hero {{ background-size:180% 180%; animation:cm-rise .6s ease both, cm-drift 18s ease-in-out infinite; }}
.cm-stat {{ animation:cm-rise .6s ease both; transition:background .2s ease, transform .2s ease; }}
.cm-stat:nth-child(1) {{ animation-delay:.12s; }} .cm-stat:nth-child(2) {{ animation-delay:.22s; }} .cm-stat:nth-child(3) {{ animation-delay:.32s; }}
.cm-stat:hover {{ background:rgba(255,255,255,.2); transform:translateY(-2px); }}
.cm-step {{ animation:cm-rise .6s ease both; }}
.cm-step:nth-child(1) {{ animation-delay:.2s; }} .cm-step:nth-child(2) {{ animation-delay:.3s; }} .cm-step:nth-child(3) {{ animation-delay:.4s; }}
.cm-card, .cm-step, .cm-hit, .cm-kpi, [data-testid="stMetric"], .cm-chip {{ transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease; }}
.cm-card:hover, .cm-step:hover, .cm-hit:hover, .cm-kpi:hover, [data-testid="stMetric"]:hover {{ transform:translateY(-4px); box-shadow:{SHADOW_LIFT}; border-color:{BLUE}; }}
.cm-card:hover {{ border-left-color:{BLUE}; }}
.cm-hit:hover {{ border-left-color:{NAVY}; }}
.cm-chip:hover {{ transform:translateY(-2px); border-color:{BLUE}; }}
.stButton > button, .stFormSubmitButton > button {{ transition:transform .15s ease, box-shadow .15s ease, background .15s ease; }}
.stButton > button:hover, .stFormSubmitButton > button:hover {{ transform:translateY(-2px); box-shadow:{SHADOW_LIFT}; }}
@media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ animation:none !important; transition:none !important; }} }}
@media (max-width: 700px) {{
  .block-container {{ padding-left:.9rem !important; padding-right:.9rem !important; padding-top:3rem !important; }}
  .cm-hero {{ padding:1.2rem 1.1rem; }}
  .cm-hero h1 {{ font-size:1.7rem; }}
  .cm-quote {{ font-size:1.02rem; margin-top:.7rem; }}
  .cm-stats, .cm-steps {{ grid-template-columns:1fr; }}
  .cm-stat .n {{ font-size:1.35rem; }}
}}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def blue_scale(value: float, vmax: float) -> str:
    """Background colour for a heat-table cell: white at 0 to deep blue at vmax (text stays readable)."""
    if vmax <= 0 or value <= 0:
        return "background-color:#ffffff;color:#9bb0c4"
    t = min(1.0, value / vmax)
    r, g, b = (int(255 + (c - 255) * t) for c in (0x00, 0x67, 0xAD))
    return f"background-color:rgb({r},{g},{b});color:{'#ffffff' if t > 0.55 else INK}"
