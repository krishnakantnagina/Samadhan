"""Pages added for the redesign: demo-aware ticket table, Area Analysis, Search. Re-exported by pages.py.

Kept in its own module so pages.py stays readable; it imports the shared helpers (Context, _badge, _go, ...) lazily to avoid a circular import.
"""

import pandas as pd
import streamlit as st

from dashboard.analytics import DEFAULT_SLA_DAYS
from dashboard.cm import area, search as S, theme
from dashboard.cm import registry as R
from dashboard.cm import ui
from dashboard.cm.departments import ALL_DEPARTMENTS
from dashboard import safe

DEMO_STATUSES = ["new", "in_progress", "resolved", "needs_review"]


def demo_ticket_table(ctx, df: pd.DataFrame, key: str) -> None:
    """Ticket list + detail for the DEMO dataset. Edits change the session copy only: nothing is written anywhere."""
    cols = [c for c in ("complaint_id", "status", "department", "district", "issue", "office_name", "created_at") if c in df]
    ev = ui.table(df[cols], width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key=f"demo-tbl-{key}-{len(df)}")
    rows = ev.selection["rows"]
    if not rows:
        return
    row = df.iloc[rows[0]]
    st.divider()
    st.subheader(row["complaint_id"])
    st.write(f"**Issue:** {safe.md(row.get('issue', '-'))}  ·  **District:** {safe.md(row.get('district', '-'))} ({safe.md(row.get('division', '-'))})  ·  **Area:** {safe.md(row.get('area_type', '-'))}")
    st.write(f"**Department:** {safe.md(row['department'])}  ·  **Office:** {safe.md(row['office_name'])}  ·  **Location precision:** {safe.md(row.get('location_quality', '-'))}")
    st.write(f"**Summary:** {safe.md(row['summary_en'])}")
    st.caption(f"Created {row['created_at']}  ·  last update {row['updated_at']}")
    store = st.session_state.get("demo_df")
    if store is None:
        return
    idx = store.index[store["complaint_id"] == row["complaint_id"]][0]
    cid = row["complaint_id"]
    new_status = st.selectbox("Status", DEMO_STATUSES, index=DEMO_STATUSES.index(row["status"]), key=f"demo-status-{key}-{cid}")
    if st.button("Save status", key=f"demo-save-{key}-{cid}"):
        store.loc[idx, ["status", "updated_at"]] = [new_status, pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")]
        st.rerun()
    if ctx.account.can_reassign:
        allowed = ctx.account.reassign_departments()
        names = sorted(set(store["department"].unique()) | {d[1] for d in ALL_DEPARTMENTS})
        names = [n for n in names if allowed is None or n in allowed]
        if names:
            to = st.selectbox("Reassign to department", names, key=f"demo-reassign-{key}-{cid}")
            if st.button("Reassign", key=f"demo-reassign-btn-{key}-{cid}"):
                store.loc[idx, ["department", "updated_at"]] = [to, pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")]
                st.rerun()
    st.caption("Demo data: changes live in this browser session only.")


def page_area(ctx) -> None:
    from dashboard.cm.pages import _badge

    st.title("Area Analysis")
    _badge(ctx)
    df = ctx.df
    if df.empty or "district" not in df:
        st.info("This data has no district column. Switch to the demo dataset in the sidebar to explore area analysis; live tickets do not carry a district yet.")
        return
    c = st.columns([2, 1, 1])
    depts = sorted(df["department"].unique())
    chosen_one = c[0].selectbox("Department", ["All", *depts], key="area-depts")
    chosen = depts if chosen_one == "All" else [chosen_one]
    window = c[1].selectbox("Period", ["Last 30 days", "Last 60 days", "Last 90 days", "All"], index=3, key="area-window")
    sla = c[2].number_input("Overdue after (days)", 1, 90, DEFAULT_SLA_DAYS, key="area-sla")
    now = pd.Timestamp.now(tz="UTC")
    f = df[df["department"].isin(chosen)]
    if window != "All" and not f.empty:
        age = (now - pd.to_datetime(f["created_at"], utc=True, format="ISO8601")).dt.days
        f = f[age <= int(window.split()[1])]
    if f.empty:
        st.warning("No tickets match these filters.")
        return
    districts = pd.DataFrame(R.rows(ctx.conn, "SELECT name, division, population_2011 FROM districts"))
    ds = area.district_summary(f, districts, now, sla)
    k = st.columns(4)
    k[0].metric("Districts with complaints", len(ds), help=f"of {len(districts)} in MP")
    worst = ds.sort_values("resolution_rate").iloc[0]
    k[1].metric("Lowest resolution rate", f"{worst['resolution_rate']}%", worst["district"], delta_color="off")
    top = ds.sort_values("overdue", ascending=False).iloc[0]
    k[2].metric("Most overdue", int(top["overdue"]), top["district"], delta_color="off")
    rate = ds.sort_values("per_100k", ascending=False).iloc[0]
    k[3].metric("Highest per 100,000 people", f"{rate['per_100k']}", rate["district"], delta_color="off")
    t_dist, t_div, t_hot, t_heat, t_loc = st.tabs(["Districts", "Divisions", "Hotspots", "Department x District", "Location precision"])
    with t_dist:
        a, b = st.columns(2)
        a.subheader("Complaints per 100,000 people")
        a.bar_chart(ds.sort_values("per_100k", ascending=False).head(15).set_index("district")["per_100k"], color=theme.BLUE)
        b.subheader("Overdue tickets")
        b.bar_chart(ds.sort_values("overdue", ascending=False).head(15).set_index("district")["overdue"], color=theme.ALERT)
        ui.table(ds, width="stretch", hide_index=True)
        st.caption("Per-100,000 rates use 2011 population from the registry. They show who reaches the system (phone, internet, awareness), not only where problems are. "
                   "No map yet: official boundaries are behind NIC tokens (see the State GIS Portal findings).")
    with t_div:
        dv = area.division_summary(ds)
        st.bar_chart(dv.set_index("division")[["received", "pending", "overdue"]], color=[theme.BLUE, theme.SKY, theme.ALERT])
        ui.table(dv, width="stretch", hide_index=True)
    with t_hot:
        c1, c2 = st.columns(2)
        win = c1.slider("Window (days)", 7, 60, 30, key="hot-win")
        minc = c2.slider("Minimum complaints in the window", 2, 10, 4, key="hot-min")
        hs = area.hotspots(f, now, win, minc)
        st.caption("A hotspot = at least this many complaints of one kind in one district in the window, and either new or 1.5x the previous window. "
                   "Simple on purpose, so an officer can check it by eye.")
        if hs.empty:
            st.success("No hotspots with these settings.")
        else:
            ui.table(hs, width="stretch", hide_index=True)
    with t_heat:
        by = st.radio("Columns", ["department", "issue"], horizontal=True, key="heat-by")
        ht = area.heat_table(f, "district", by, top_rows=15, top_cols=8)
        vmax = float(ht.to_numpy().max()) if not ht.empty else 0
        ui.table(ht.style.map(lambda v: theme.blue_scale(v, vmax)), width="stretch")
        st.caption("Busiest 15 districts by busiest 8 departments (or issues). Darker = more complaints.")
    with t_loc:
        st.bar_chart(area.location_mix(f), color=theme.SKY)
        st.caption("How precisely citizens said where the problem is. 'district' and 'unknown' tickets cannot be mapped or routed below district level: "
                   "a village directory (LGD codes) would raise this precision.")


def _search_index(ctx):
    key = tuple(ctx.conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM audit_log").fetchone())
    cached = st.session_state.get("search_index")
    if not cached or cached[0] != key:
        st.session_state["search_index"] = (key, S.build_index(ctx.conn))
    return st.session_state["search_index"][1]


def page_search(ctx) -> None:
    from dashboard.cm.pages import _go

    st.title("Search")
    acct = ctx.account
    q = st.text_input("Search departments, services, schemes, districts, offices and tickets (English or हिन्दी)", value=st.session_state.get("global_q", ""),
                      key="search-page-q", placeholder="bijli, पानी, pension, ration card, Sagar, SMD-0007 ...")
    allowed = S.allowed_kinds(acct.role)
    kinds = tuple(st.multiselect("Show", list(allowed), default=list(allowed), key="search-kinds"))
    if not q.strip():
        st.write("Try:")
        st.markdown("".join(f'<span class="cm-chip">{x}</span>' for x in ("bijli", "पानी", "pension", "ration card", "caste certificate", "Sagar", "handpump", "लाडली लक्ष्मी", "DEMO-0012")),
                    unsafe_allow_html=True)
        st.caption("Words match in English and Hindi (bijli = बिजली = electricity), by prefix, and with small typos. Every word you type must match.")
        return
    entries = _search_index(ctx) + S.ticket_entries(ctx.df)
    groups = S.search(entries, q, kinds or allowed)
    groups = {k: [h for h in v if S.visible(h.entry, acct.role, acct.dept_id)] for k, v in groups.items()}
    groups = {k: v for k, v in groups.items() if v}
    if not groups:
        st.warning("Nothing found. Try fewer words, or the Hindi or English form of the word.")
        return
    st.caption(f"{sum(len(v) for v in groups.values())} result(s) for '{safe.md(q)}'")
    labels = {"department": "Departments", "service": "Services", "scheme": "Schemes", "district": "Districts", "office": "Sub-offices", "ticket": "Tickets"}
    for kind in S.KINDS:
        hits = groups.get(kind)
        if not hits:
            continue
        st.subheader(labels[kind])
        for i, h in enumerate(hits):
            e = h.entry
            left, right = st.columns([6, 1])
            left.markdown(f'<div class="cm-hit"><span class="k">{safe.h(kind)}</span><div class="t">{safe.h(e.title)}</div><div class="s">{safe.h(e.subtitle)}</div></div>', unsafe_allow_html=True)
            if ctx.nav and right.button("Open", key=f"open-{kind}-{i}-{e.ref}"):
                if kind == "ticket":
                    _go(ctx, "tickets", ticket_q=e.ref)
                elif kind == "district":
                    _go(ctx, "geography")
                elif e.dept_id and acct.role == "cm_admin":
                    _go(ctx, "departments", open_dept=e.dept_id)
                elif e.dept_id and acct.role == "dept_head":
                    _go(ctx, "my_department")
                else:
                    _go(ctx, "services")
