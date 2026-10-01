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
LIGHTER = "#eceff3"  # page background: light grey
GREY = "#6b7787"
GREY_LIGHT = "#d5dbe3"
ORANGE = BLUE  # kept as names so old imports work; the palette is blue / white / grey only
DEEP_ORANGE = NAVY
ALERT = "#44546a"  # dark slate for "bad" values
INK = "#0b1f33"
MUTED = "#12304d"
CHART_COLOURS = [BLUE, GREY, SKY, NAVY, "#9fb3c8", ALERT]

CSS = f"""
<style>
:root {{ --navy:{NAVY}; --blue:{BLUE}; --sky:{SKY}; --bright:{BRIGHT}; --light:{LIGHT}; --orange:{ORANGE}; --deep-orange:{DEEP_ORANGE}; --ink:{INK}; }}
[data-testid="stAppViewContainer"] {{ background:{LIGHTER}; color:{INK}; }}
[data-testid="stHeader"] {{ background:{LIGHTER}; border-bottom:0; box-shadow:none; }}
.stAppDeployButton, [data-testid="stAppDeployButton"] {{ display:none; }}
.cm-card .nm {{ display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-weight:700; color:{NAVY}; min-height:2.9em; }}
[data-testid="stSidebar"] {{ background:linear-gradient(180deg,{NAVY} 0%,#12427f 100%); }}
[data-testid="stSidebar"] * {{ color:#eaf4ff !important; }}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {{ color:{INK} !important; background:#fff !important; }}
[data-testid="stSidebarNav"] a[aria-current="page"], [data-testid="stSidebarNav"] a[data-testid="stSidebarNavLink"][aria-current="page"] {{ background:rgba(255,255,255,.16) !important; border-left:4px solid #ffffff; }}
h1, h2, h3 {{ color:{NAVY}; letter-spacing:.2px; }}
h1 {{ border-bottom:4px solid {BLUE}; padding-bottom:.25rem; display:inline-block; }}
[data-testid="stMetric"] {{ background:#fff; border:1px solid {GREY_LIGHT}; border-top:3px solid {NAVY}; border-radius:3px; padding:.7rem .9rem; box-shadow:none; }}
[data-testid="stMetricValue"] {{ color:{NAVY}; font-weight:700; }}
[data-testid="stMetricLabel"] p {{ color:{MUTED}; }}
.stButton > button, .stFormSubmitButton > button {{ background:{BLUE}; color:#fff; border:0; border-radius:3px; font-weight:600; }}
.stButton > button:hover, .stFormSubmitButton > button:hover {{ background:{NAVY}; color:#fff; }}
[data-baseweb="tab"][aria-selected="true"] {{ color:{NAVY}; border-bottom:3px solid {BLUE}; }}
/* inputs, selects and text areas: thick, dark borders */
.stTextInput [data-baseweb="input"], .stNumberInput [data-baseweb="input"], .stTextArea [data-baseweb="textarea"], .stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div, .stDateInput [data-baseweb="input"] {{ border:1.5px solid {NAVY} !important; border-radius:6px !important; background:#ffffff !important; }}
.stTextInput input, .stNumberInput input, .stTextArea textarea {{ color:{INK} !important; }}
[data-testid="stSidebar"] .stTextInput [data-baseweb="input"], [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div {{ border:1.5px solid #9fc3e8 !important; }}
/* tables: dark frame; header colours come from .streamlit/config.toml */
[data-testid="stDataFrame"] {{ border:1.5px solid {NAVY}; border-radius:6px; background:#ffffff; }}
/* readable text on the grey page */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *, .stCaption, .stCaption *, [data-testid="stAppViewContainer"] small {{ color:#0b1f33 !important; opacity:1 !important; }}
[data-testid="stAppViewContainer"] label, [data-testid="stAppViewContainer"] [data-testid="stWidgetLabel"] p {{ color:{INK} !important; font-weight:600; }}
[data-baseweb="tab"] {{ color:{INK}; font-weight:600; }}
hr {{ border-color:{GREY} !important; opacity:.35; }}
/* charts: white panel */
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {{ background:#fff; border:1px solid {GREY_LIGHT}; border-radius:3px; padding:.6rem .7rem; }}
.cm-hero {{ background:linear-gradient(120deg,{NAVY} 0%,{BLUE} 62%,{SKY} 100%); color:#fff; border-radius:4px; padding:2rem 2.2rem; position:relative; overflow:hidden; }}
.cm-hero h1 {{ color:#fff; border:0; font-size:2.6rem; margin:0; }}
.cm-hero .tag {{ color:#cfe0f2; font-weight:600; letter-spacing:1.4px; text-transform:uppercase; font-size:.8rem; }}
.cm-quote {{ font-size:1.25rem; line-height:1.5; margin:1rem 0 .2rem; max-width:46rem; position:relative; z-index:1; }}
.cm-quote-hi {{ color:#cfe6ff; font-size:1.05rem; position:relative; z-index:1; }}
.cm-card {{ background:#fff; border:1px solid {GREY_LIGHT}; border-left:5px solid {NAVY}; border-radius:3px; padding:.9rem 1rem; height:100%; box-shadow:none; }}
.cm-card b {{ color:{NAVY}; }}
.cm-card small {{ color:{MUTED}; }}
.cm-stat {{ background:rgba(255,255,255,.10); border:0; border-top:3px solid #ffffff; border-radius:3px; padding:.7rem 1rem; text-align:center; position:relative; z-index:1; }}
.cm-stat .n {{ font-size:1.7rem; font-weight:700; color:#fff; }}
.cm-stat .l {{ font-size:.78rem; color:#cfe6ff; letter-spacing:.4px; }}
.cm-chip {{ display:inline-block; background:{LIGHT}; color:{NAVY}; border:1px solid {GREY_LIGHT}; border-radius:3px; padding:.15rem .7rem; margin:.15rem .2rem; font-size:.82rem; }}
.cm-badge-demo {{ display:inline-block; background:{GREY}; color:#fff; border-radius:3px; padding:.1rem .55rem; font-size:.75rem; font-weight:700; letter-spacing:.6px; }}
.cm-badge-live {{ display:inline-block; background:{BLUE}; color:#fff; border-radius:3px; padding:.1rem .55rem; font-size:.75rem; font-weight:700; letter-spacing:.6px; }}
.cm-hit {{ background:#fff; border:1px solid {GREY_LIGHT}; border-left:3px solid {BLUE}; border-radius:3px; padding:.6rem .85rem; margin:.3rem 0; }}
.cm-hit .k {{ color:{BLUE}; font-size:.72rem; font-weight:700; letter-spacing:.8px; text-transform:uppercase; }}
.cm-hit .t {{ color:{NAVY}; font-weight:600; }}
.cm-hit .s {{ color:{MUTED}; font-size:.85rem; }}
/* page spacing: Streamlit's default top gap is large */
.block-container {{ padding-top:3.1rem !important; padding-bottom:2rem !important; max-width:1240px; }}
[data-testid="stHeader"] {{ height:2.4rem; }}
.cm-topbar {{ display:flex; align-items:center; gap:.7rem; padding:.2rem 0 .1rem; }}
.cm-topbar .mark {{ width:38px; height:38px; border-radius:4px; background:{NAVY}; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1.2rem; }}
.cm-topbar .nm {{ font-weight:800; color:{NAVY}; font-size:1.15rem; line-height:1.1; }}
.cm-topbar .sub {{ color:{MUTED}; font-size:.78rem; letter-spacing:.4px; }}
.cm-stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:.7rem; margin-top:1.1rem; }}
.cm-hero {{ margin-top:.5rem; }}
.cm-steps {{ display:grid; grid-template-columns:repeat(3,1fr); gap:.8rem; margin:1rem 0 .4rem; }}
.cm-step {{ background:#fff; border:1px solid {GREY_LIGHT}; border-top:3px solid {NAVY}; border-radius:3px; padding:.9rem 1rem; }}
.cm-step .no {{ color:{BLUE}; font-weight:800; font-size:.8rem; letter-spacing:1px; }}
.cm-step b {{ display:block; color:{NAVY}; margin:.15rem 0 .25rem; }}
.cm-step small {{ color:{MUTED}; }}
.cm-facts {{ display:flex; flex-wrap:wrap; gap:.4rem; margin-top:.9rem; position:relative; z-index:1; }}
.cm-facts span {{ background:rgba(255,255,255,.14); border-top:2px solid #fff; border-radius:3px; padding:.25rem .65rem; font-size:.8rem; color:#fff; }}
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
.cm-card, .cm-step, .cm-hit, [data-testid="stMetric"], .cm-chip {{ transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease; }}
.cm-card:hover, .cm-step:hover, .cm-hit:hover, [data-testid="stMetric"]:hover {{ transform:translateY(-4px); box-shadow:0 12px 24px rgba(11,46,89,.18); border-color:{BLUE}; }}
.cm-card:hover {{ border-left-color:{BLUE}; }}
.cm-hit:hover {{ border-left-color:{NAVY}; }}
.cm-chip:hover {{ transform:translateY(-2px); border-color:{BLUE}; }}
.stButton > button, .stFormSubmitButton > button {{ transition:transform .15s ease, box-shadow .15s ease, background .15s ease; }}
.stButton > button:hover, .stFormSubmitButton > button:hover {{ transform:translateY(-2px); box-shadow:0 6px 14px rgba(11,46,89,.28); }}
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
