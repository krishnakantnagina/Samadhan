"""Blue / light-blue / orange theme for the CM-office system.

Government look: deep navy and blue lead, soft blue-grey page, white cards. Orange is only a thin accent (menu marker, badges), never a fill for
buttons or backgrounds; a saffron-white-green hairline sits at the very top like many Indian government sites. Blues follow the MP State GIS Portal palette. `inject()` adds the CSS once per page run; charts use CHART_COLOURS.
"""

import streamlit as st

NAVY = "#0b2e59"
BLUE = "#0b5cab"
SKY = "#3b8fd9"
BRIGHT = "#008eff"
LIGHT = "#e3eefa"
LIGHTER = "#86A5B8"  # page background chosen by the Lead
ORANGE = "#f28c1b"
DEEP_ORANGE = "#d9531e"
ALERT = "#c4472f"
INK = "#0b1f33"
MUTED = "#12304d"
CHART_COLOURS = [BLUE, SKY, NAVY, BRIGHT, ORANGE, ALERT]

CSS = f"""
<style>
:root {{ --navy:{NAVY}; --blue:{BLUE}; --sky:{SKY}; --bright:{BRIGHT}; --light:{LIGHT}; --orange:{ORANGE}; --deep-orange:{DEEP_ORANGE}; --ink:{INK}; }}
[data-testid="stAppViewContainer"] {{ background:{LIGHTER}; color:{INK}; }}
[data-testid="stHeader"] {{ background:transparent; }}
.stApp::before {{ content:""; position:fixed; top:0; left:0; right:0; height:5px; z-index:999999; background:linear-gradient(90deg,#ff9933 0 33.3%,#ffffff 33.3% 66.6%,#138808 66.6% 100%); }}
.stAppDeployButton, [data-testid="stAppDeployButton"] {{ display:none; }}
.cm-card .nm {{ display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-weight:700; color:{NAVY}; min-height:2.9em; }}
[data-testid="stSidebar"] {{ background:linear-gradient(180deg,{NAVY} 0%,#12427f 100%); }}
[data-testid="stSidebar"] * {{ color:#eaf4ff !important; }}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {{ color:{INK} !important; background:#fff !important; }}
[data-testid="stSidebarNav"] a[aria-current="page"], [data-testid="stSidebarNav"] a[data-testid="stSidebarNavLink"][aria-current="page"] {{ background:rgba(255,152,0,.22) !important; border-left:4px solid {ORANGE}; }}
h1, h2, h3 {{ color:{NAVY}; letter-spacing:.2px; }}
h1 {{ border-bottom:4px solid {BLUE}; padding-bottom:.25rem; display:inline-block; }}
[data-testid="stMetric"] {{ background:#fff; border:1px solid #cfe3f3; border-top:4px solid {BLUE}; border-radius:10px; padding:.7rem .9rem; box-shadow:0 1px 3px rgba(0,57,112,.08); }}
[data-testid="stMetricValue"] {{ color:{NAVY}; font-weight:700; }}
[data-testid="stMetricLabel"] p {{ color:{MUTED}; }}
.stButton > button, .stFormSubmitButton > button {{ background:{BLUE}; color:#fff; border:0; border-radius:8px; font-weight:600; }}
.stButton > button:hover, .stFormSubmitButton > button:hover {{ background:{NAVY}; color:#fff; }}
[data-baseweb="tab"][aria-selected="true"] {{ color:{NAVY}; border-bottom:3px solid {BLUE}; }}
/* inputs, selects and text areas: thick, dark borders */
.stTextInput [data-baseweb="input"], .stNumberInput [data-baseweb="input"], .stTextArea [data-baseweb="textarea"], .stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div, .stDateInput [data-baseweb="input"] {{ border:1.5px solid {NAVY} !important; border-radius:6px !important; background:#ffffff !important; }}
.stTextInput input, .stNumberInput input, .stTextArea textarea {{ color:{INK} !important; }}
[data-testid="stSidebar"] .stTextInput [data-baseweb="input"], [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div {{ border:1.5px solid #9fc3e8 !important; }}
/* tables: dark frame; header colours come from .streamlit/config.toml */
[data-testid="stDataFrame"] {{ border:1.5px solid {NAVY}; border-radius:6px; background:#ffffff; }}
/* readable text on the #86A5B8 page */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *, .stCaption, .stCaption *, [data-testid="stAppViewContainer"] small {{ color:#0b1f33 !important; opacity:1 !important; }}
[data-testid="stAppViewContainer"] label, [data-testid="stAppViewContainer"] [data-testid="stWidgetLabel"] p {{ color:{INK} !important; font-weight:600; }}
[data-baseweb="tab"] {{ color:{INK}; font-weight:600; }}
hr {{ border-color:{NAVY} !important; opacity:.35; }}
.cm-hero {{ background:linear-gradient(120deg,{NAVY} 0%,{BLUE} 62%,{SKY} 100%); color:#fff; border-radius:16px; padding:2rem 2.2rem; position:relative; overflow:hidden; }}
.cm-hero:after {{ content:""; position:absolute; right:-70px; top:-70px; width:300px; height:300px; border-radius:50%; background:radial-gradient(circle, rgba(120,190,255,.55) 0%, rgba(120,190,255,.22) 40%, rgba(120,190,255,0) 70%); }}
.cm-hero h1 {{ color:#fff; border:0; font-size:2.6rem; margin:0; }}
.cm-hero .tag {{ color:#ffd9a0; font-weight:600; letter-spacing:1.4px; text-transform:uppercase; font-size:.8rem; }}
.cm-quote {{ font-size:1.25rem; line-height:1.5; margin:1rem 0 .2rem; max-width:46rem; position:relative; z-index:1; }}
.cm-quote-hi {{ color:#cfe6ff; font-size:1.05rem; position:relative; z-index:1; }}
.cm-card {{ background:#fff; border:1px solid #cfe3f3; border-left:5px solid {BLUE}; border-radius:12px; padding:.9rem 1rem; height:100%; box-shadow:0 1px 3px rgba(0,57,112,.07); }}
.cm-card b {{ color:{NAVY}; }}
.cm-card small {{ color:{MUTED}; }}
.cm-stat {{ background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.25); border-radius:12px; padding:.7rem 1rem; text-align:center; position:relative; z-index:1; }}
.cm-stat .n {{ font-size:1.7rem; font-weight:700; color:#fff; }}
.cm-stat .l {{ font-size:.78rem; color:#cfe6ff; letter-spacing:.4px; }}
.cm-chip {{ display:inline-block; background:{LIGHT}; color:{NAVY}; border:1px solid #b9d7ee; border-radius:999px; padding:.15rem .7rem; margin:.15rem .2rem; font-size:.82rem; }}
.cm-badge-demo {{ display:inline-block; background:{ORANGE}; color:#fff; border-radius:6px; padding:.1rem .55rem; font-size:.75rem; font-weight:700; letter-spacing:.6px; }}
.cm-badge-live {{ display:inline-block; background:#1b8a5a; color:#fff; border-radius:6px; padding:.1rem .55rem; font-size:.75rem; font-weight:700; letter-spacing:.6px; }}
.cm-hit {{ background:#fff; border:1px solid #cfe3f3; border-radius:10px; padding:.6rem .85rem; margin:.3rem 0; }}
.cm-hit .k {{ color:{BLUE}; font-size:.72rem; font-weight:700; letter-spacing:.8px; text-transform:uppercase; }}
.cm-hit .t {{ color:{NAVY}; font-weight:600; }}
.cm-hit .s {{ color:{MUTED}; font-size:.85rem; }}
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
