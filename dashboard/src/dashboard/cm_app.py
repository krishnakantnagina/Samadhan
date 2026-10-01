"""Samadhan CM-office central system: side-menu app over all departments, sub-offices and tickets.

Run (from dashboard/):  uv run streamlit run src/dashboard/cm_app.py --server.address localhost
Sign in with a demo account (local-research/DEMO_ACCOUNTS.md) or user `admin` + DASHBOARD_PASSWORD.
Build the registry first if it is missing:  uv run python -m dashboard.cm.build_cli
The sidebar switches between the DEMO dataset (360 invented tickets, default) and the LIVE Samadhan database.
Design and limits: local-research/CM_OFFICE_DASHBOARD_DESIGN.md. The older officer dashboard (app.py) still runs unchanged.
"""

import os
import random
from functools import partial

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from dashboard import app as legacy
from dashboard.cm import accounts, demo_data, home, pages, registry, theme

load_dotenv()

MENU = [  # (group, page key, title, icon, function)
    ("Overview", "command", "Command Centre", ":material/dashboard:", pages.page_command),
    ("Overview", "search", "Search", ":material/search:", pages.page_search),
    ("Overview", "area", "Area Analysis", ":material/location_on:", pages.page_area),
    ("Management", "departments", "Departments", ":material/account_balance:", pages.page_departments),
    ("Management", "my_department", "My Department", ":material/account_balance:", pages.page_my_department),
    ("Management", "geography", "Geography and Coverage", ":material/map:", pages.page_geography),
    ("Management", "services", "Services", ":material/list_alt:", pages.page_services),
    ("Operations", "human_eval", "Human Evaluation", ":material/fact_check:", pages.page_human_eval),
    ("Operations", "tickets", "Tickets and Routing", ":material/confirmation_number:", pages.page_tickets),
    ("Intelligence", "routing_lab", "Routing Lab", ":material/alt_route:", pages.page_routing_lab),
    ("Intelligence", "public_flow", "Public Flow", ":material/monitoring:", pages.page_public_flow),
    ("System", "data", "Data and Sources", ":material/database:", pages.page_data),
    ("System", "accounts", "Accounts and Roles", ":material/group:", pages.page_accounts),
]
DEMO_LABEL, LIVE_LABEL = "Demo data (360 invented tickets)", "Live Samadhan database"


@st.cache_resource
def _registry():
    return registry.connect()


@st.cache_data
def _home_data() -> home.HomeData:
    return home.load()


def _login_screen() -> accounts.Account:
    """Home page + sign-in. Real CM Helpline figures and scheme names, original quotes; nothing else is invented."""
    if st.session_state.get("cm_account"):
        return st.session_state["cm_account"]
    theme.inject()
    hd = _home_data()
    seed = st.session_state.setdefault("quote_seed", random.randrange(1000))
    en, hi = home.pick_quote(seed)
    left, right = st.columns([3, 2], gap="large")
    with left:
        stats = ""
        if hd.registered:
            stats = "".join(f'<div class="cm-stat"><div class="n">{n}</div><div class="l">{label}</div></div>' for n, label in (
                (home.indian(hd.registered), "COMPLAINTS REGISTERED (CM HELPLINE 181)"), (home.indian(hd.resolved), "RESOLVED"), (f"{hd.resolution_rate}%", "RESOLUTION RATE")))
            stats = f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:.7rem;margin-top:1.2rem">{stats}</div>'
        st.markdown(f'<div class="cm-hero"><div class="tag">Madhya Pradesh · CM Office</div><h1>समाधान · Samadhan</h1>'
                    f'<div class="cm-quote">“{en}”</div><div class="cm-quote-hi">{hi}</div>{stats}</div>', unsafe_allow_html=True)
        if st.button("↻ Another line"):
            st.session_state["quote_seed"] = seed + 1
            st.rerun()
        st.caption(hd.source_note)
    with right:
        st.subheader("Sign in")
        user = st.text_input("Username")
        pw = st.text_input("Password", type="password")
        if st.button("Log in", use_container_width=True):
            found = accounts.authenticate(user, pw, accounts.load_accounts(), legacy_password=os.environ.get("DASHBOARD_PASSWORD"))
            if found:
                st.session_state["cm_account"] = found
                st.rerun()
            st.error("Wrong username or password.")
        st.caption("Demo accounts are listed in local-research/DEMO_ACCOUNTS.md.")
        st.markdown('<div class="cm-card"><b>What Samadhan does</b><br><small>1. A citizen describes the problem in their own words.<br>'
                    '2. Samadhan confirms what it understood and finds the right department and office.<br>'
                    '3. The complaint lands on an officer\'s desk, and the CM office can see it all in one place.</small></div>', unsafe_allow_html=True)
    if hd.schemes:
        st.markdown("### From the CM Helpline scheme directory")
        cards = st.columns(4)
        for col, s in zip(cards, home.spotlight(hd, 4, seed), strict=False):
            col.markdown(f'<div class="cm-card"><div class="nm" title="{s["scheme"]}">{s["scheme"]}</div><small>{s["department"]}</small></div>', unsafe_allow_html=True)
        st.markdown("".join(f'<span class="cm-chip">{d} · {n}</span>' for d, n in hd.by_department[:12]), unsafe_allow_html=True)
        st.caption(f"{len(hd.schemes)} schemes across {len(hd.by_department)} departments (cmhelpline.mp.gov.in, scraped 1 Oct 2026). Official details: {home.SCHEME_PAGE}")
    st.stop()


def _load_tickets(conn, account: accounts.Account, demo: bool) -> tuple[pd.DataFrame, str | None]:
    """The ticket frame for the chosen dataset. Demo rows live in the session (edits stay there); live rows come from the existing dashboard code."""
    if demo:
        if "demo_df" not in st.session_state:
            st.session_state["demo_df"] = demo_data.from_registry(conn)
        return st.session_state["demo_df"], None
    try:
        return legacy._cached_tickets(), None
    except Exception as exc:  # noqa: BLE001 -- a database hiccup must not lock officers out of the registry pages
        return pd.DataFrame(columns=["complaint_id", "status", "department", "office_name", "created_at", "updated_at"]), str(exc)


def main() -> None:
    st.set_page_config(page_title="Samadhan — CM Office", layout="wide", page_icon="🏛️")
    account = _login_screen()
    theme.inject()
    conn = _registry()
    if not conn.execute("SELECT 1 FROM departments LIMIT 1").fetchone():
        st.error("The registry is empty. Run `uv run python -m dashboard.cm.build_cli` from dashboard/, then reload.")
        st.stop()

    with st.sidebar:
        st.markdown("### 🏛️ Samadhan")
        st.caption(f"**{account.username}** · {account.role}")
        st.text_input("🔍 Search everything", key="global_q_input", placeholder="bijli, पानी, SMD-0007 …", on_change=lambda: st.session_state.update(go_search=True, global_q=st.session_state["global_q_input"]))
        demo = st.radio("Data", [DEMO_LABEL, LIVE_LABEL], key="dataset") == DEMO_LABEL
        if st.button("Log out"):
            for k in ("cm_account", "demo_df", "search_index"):
                st.session_state.pop(k, None)
            st.rerun()

    all_tickets, error = _load_tickets(conn, account, demo)
    df = accounts.scope_tickets(all_tickets, account) if not all_tickets.empty else all_tickets
    ctx = pages.Context(account=account, conn=conn, df=df, tickets_error=error, legacy=legacy, is_demo=demo)

    groups: dict[str, list] = {}
    by_key: dict[str, st.Page] = {}
    for group, key, title, icon, fn in MENU:
        if account.can_open(key):
            page = st.Page(partial(fn, ctx), title=title, icon=icon, url_path=key, default=(key == "command"))
            groups.setdefault(group, []).append(page)
            by_key[key] = page
    ctx.nav = by_key
    nav = st.navigation(groups)
    if st.session_state.pop("go_search", False) and "search" in by_key:
        st.switch_page(by_key["search"])
    nav.run()


if __name__ == "__main__":
    main()
