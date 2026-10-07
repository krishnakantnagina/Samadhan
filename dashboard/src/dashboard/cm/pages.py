"""Pages of the CM-office system. Each `page_*` takes a Context and draws one screen; cm_app.py wires them to the side menu by role.

Data: live tickets (Supabase, read through the existing dashboard code) scoped by the signed-in account, plus the local registry
(departments, services, geography, sub-offices) and public reference numbers scraped from mpedistrict.gov.in.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd
import streamlit as st

from dashboard.analytics import DEFAULT_SLA_DAYS, ageing, daily_trend, department_summary, totals
from dashboard.cm import registry as R
from dashboard.cm import ui
from dashboard.cm import theme  # noqa: F401  (used by pages_extra)
from dashboard.cm.accounts import Account
from dashboard.cm.departments import ALL_DEPARTMENTS, LIVE_MAP, ROUTING_HINTS

SNAPSHOT_DIR = R.DATA_DIR / "mpedistrict"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
STATUS_COLOURS = {"live": "🟢", "demo": "🟡", "planned": "🔵", "catalogued": "⚪"}


@dataclass
class Context:
    account: Account
    conn: "R.sqlite3.Connection"
    df: pd.DataFrame  # tickets this account may see (already scoped)
    tickets_error: str | None = None
    legacy: object | None = None  # dashboard.app module, for the existing ticket table/detail/map
    is_demo: bool = False  # True when df is the synthetic DEMO dataset (never the live database)
    nav: dict | None = None  # page key -> st.Page, so search results can open pages


def _name_for_live(dept_id: str) -> str | None:
    return next((k for k, v in LIVE_MAP.items() if v == dept_id), None)


def _snapshot() -> dict | None:
    files = sorted(SNAPSHOT_DIR.glob("live_stats_snapshot_*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def _typesafe_key() -> str | None:
    """TYPESAFE_API_KEY from the environment, else from local-research/.env (git-excluded). Never shown."""
    if os.environ.get("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"]
    env = R.REPO_ROOT / "local-research" / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def _badge(ctx: Context) -> None:
    st.markdown('<span class="cm-badge-demo">DEMO DATA: invented for exploration, not real complaints</span>' if ctx.is_demo
                else '<span class="cm-badge-live">LIVE DATA: Samadhan database</span>', unsafe_allow_html=True)


def _go(ctx: Context, page: str, **state) -> None:
    """Open another page of the side menu, optionally passing session state (used by search results)."""
    st.session_state.update(state)
    if ctx.nav and page in ctx.nav:
        st.switch_page(ctx.nav[page])


def _need_tickets(ctx: Context) -> bool:
    if ctx.tickets_error:
        st.error(f"Could not load tickets: {ctx.tickets_error}")
        return False
    return True


# --- 1. Command centre ------------------------------------------------------------------------------------------

def page_command(ctx: Context) -> None:
    st.title("Command Centre")
    _badge(ctx)
    st.caption(f"Signed in as **{ctx.account.username}** ({ctx.account.role}). You see: " + {
        "cm_admin": "all departments.", "dept_head": f"{ctx.account.department} only.",
        "office_officer": f"{ctx.account.department}, {ctx.account.office_name} only.",
        "evaluator": "the Human Evaluation queue and every ticket that needs review."}[ctx.account.role])
    if ctx.account.role == "cm_admin":
        ov = R.departments_overview(ctx.conn)
        c = st.columns(5)
        c[0].metric("Departments", len(ov), help=f"{sum(d['official45'] for d in ov)} on mp.gov.in's list + {sum(1 - d['official45'] for d in ov)} seen on other portals")
        c[1].metric("Live / demo in Samadhan", sum(d["status"] in ("live", "demo") for d in ov))
        c[2].metric("Services catalogued", sum(d["services_mp"] for d in ov), help="mp.gov.in/services")
        c[3].metric("Districts / divisions", f"{len(R.rows(ctx.conn, 'SELECT 1 FROM districts'))} / {len(R.rows(ctx.conn, 'SELECT 1 FROM divisions'))}")
        c[4].metric("Sub-offices registered", len(R.rows(ctx.conn, "SELECT 1 FROM offices")), help="All demo today: no official office list exists for us yet")
        st.divider()
    if not _need_tickets(ctx):
        return
    if ctx.df.empty:
        st.info("No tickets in your scope yet.")
        return
    waiting = int((ctx.df["status"] == "needs_review").sum())
    if waiting and ctx.account.can_open("human_eval"):
        w1, w2 = st.columns([5, 1])
        w1.warning(f"{waiting} complaint(s) are waiting for human evaluation.")
        if ctx.nav and w2.button("Open queue"):
            _go(ctx, "human_eval")
    sla = st.number_input("Overdue after (days)", 1, 90, DEFAULT_SLA_DAYS, help="21 days is CPGRAMS's national resolution time; MP Lok Seva deadlines vary per service.")
    now = pd.Timestamp.now(tz="UTC")
    summary = department_summary(ctx.df, now, sla)
    k = totals(summary)
    cols = st.columns(5)
    for col, (label, key) in zip(cols, (("Received", "received"), ("Resolved", "resolved"), ("Pending", "pending"), ("Overdue", "overdue")), strict=False):
        col.metric(label, k[key])
    cols[4].metric("Resolution rate", f"{k['resolution_rate']}%")
    st.subheader("By department")
    ui.table(summary, width="stretch", hide_index=True)
    left, right = st.columns(2)
    left.subheader("Pending by age")
    left.bar_chart(ageing(ctx.df, now).set_index("age"))
    right.subheader("Received, last 30 days")
    right.line_chart(daily_trend(ctx.df, now))


# --- 2. Departments ---------------------------------------------------------------------------------------------

def _department_detail(ctx: Context, dept_id: str, *, editable: bool) -> None:
    d = R.rows(ctx.conn, "SELECT * FROM departments WHERE id=?", (dept_id,))[0]
    st.subheader(f"{d['name_en']}  ·  {d['name_hi']}")
    st.caption(f"{STATUS_COLOURS[d['status']]} {d['status']}" + ("" if d["official45"] else "  ·  not on mp.gov.in's list of 45 (seen on other portals)")
               + (f"  ·  Samadhan name: {d['live_name']}" if d["live_name"] else ""))
    t_sum, t_svc, t_off, t_tix = st.tabs(["Summary", "Services", "Sub-offices", "Tickets"])
    with t_sum:
        aliases = R.rows(ctx.conn, "SELECT source, alias, score FROM aliases WHERE dept_id=? ORDER BY source", (dept_id,))
        st.write("**Names used for this department on other portals** (score 1.0 exact, 0.9 reviewed alias, else fuzzy):")
        ui.table(pd.DataFrame(aliases), width="stretch", hide_index=True) if aliases else st.caption("none matched")
        if editable:
            with st.form(f"dept-edit-{dept_id}"):
                status = st.selectbox("Onboarding status", R.DEPT_STATUSES, index=R.DEPT_STATUSES.index(d["status"]))
                notes = st.text_area("Notes", d["notes"])
                if st.form_submit_button("Save"):
                    R.set_department(ctx.conn, dept_id, status=status, notes=notes, actor=ctx.account.username)
                    st.success("Saved (recorded in the audit log).")
                    st.rerun()
        elif d["notes"]:
            st.write("**Notes:**", d["notes"])
    with t_svc:
        src = st.radio("Source", ["mp.gov.in", "mpedistrict", "cmhelpline"], horizontal=True, key=f"svc-src-{dept_id}",
                       help="mpedistrict has the legal deadlines, fees and documents; mp.gov.in is the full catalogue; cmhelpline lists schemes")
        svc = R.department_services(ctx.conn, dept_id, src)
        st.caption(f"{len(svc)} from {src}")
        if svc:
            cols = ["title", "category", "deadline_urban", "deadline_rural", "fee", "apply_url"] if src == "mpedistrict" else ["title", "category", "apply_url"]
            ui.table(pd.DataFrame(svc)[cols], width="stretch", hide_index=True)
    with t_off:
        offices = R.rows(ctx.conn, "SELECT id, level, district, name, status, source, notes FROM offices WHERE dept_id=? ORDER BY district, level", (dept_id,))
        if offices:
            ui.table(pd.DataFrame(offices), width="stretch", hide_index=True)
        else:
            st.info("No sub-offices registered. They are never guessed: add one only when you have it from an official source.")
        if editable:
            with st.form(f"office-add-{dept_id}"):
                c = st.columns(4)
                level = c[0].selectbox("Level", R.OFFICE_LEVELS, index=R.OFFICE_LEVELS.index("district"))
                district = c[1].selectbox("District", ["-"] + [r["name"] for r in R.rows(ctx.conn, "SELECT name FROM districts ORDER BY name")])
                name = c[2].text_input("Office name")
                status = c[3].selectbox("Status", R.OFFICE_STATUSES, index=R.OFFICE_STATUSES.index("unverified"))
                note = st.text_input("Source / note (who confirmed it?)")
                if st.form_submit_button("Add sub-office"):
                    try:
                        R.add_office(ctx.conn, dept_id=dept_id, level=level, district=None if district == "-" else district, name=name, status=status,
                                     notes=note, actor=ctx.account.username)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            manual = [o for o in offices if o["source"] == "manual"]
            if manual:
                pick = st.selectbox("Remove a manually added office", ["-"] + [f"{o['id']}: {o['name']}" for o in manual], key=f"off-del-{dept_id}")
                if pick != "-" and st.button("Remove", key=f"off-del-btn-{dept_id}"):
                    R.delete_office(ctx.conn, int(pick.split(":")[0]), actor=ctx.account.username)
                    st.rerun()
    with t_tix:
        live = d["live_name"]
        if not live:
            st.info("Samadhan does not route complaints to this department yet (no service spec / office rows).")
        elif _need_tickets(ctx):
            mine = ctx.df[ctx.df["department"] == live]
            st.caption(f"{len(mine)} ticket(s) for {live}")
            if not mine.empty:
                ui.table(mine[["complaint_id", "status", "office_name", "summary_en", "created_at"]], width="stretch", hide_index=True)


def page_departments(ctx: Context) -> None:
    st.title("Departments")
    opened = st.session_state.get("open_dept")
    if opened:  # arrived from a search result
        if st.button("Close this department"):
            st.session_state.pop("open_dept", None)
            st.rerun()
        _department_detail(ctx, opened, editable=True)
        st.divider()
    ov = pd.DataFrame(R.departments_overview(ctx.conn))
    if _need_tickets(ctx) and not ctx.df.empty:
        t = ctx.df.groupby("department").agg(tickets=("status", "size"), pending=("status", lambda s: int((s != "resolved").sum()))).reset_index()
        ov = ov.merge(t, how="left", left_on="live_name", right_on="department").drop(columns=["department"])
    else:
        ov["tickets"], ov["pending"] = None, None
    ov["tickets"] = ov["tickets"].fillna(0).astype(int)
    ov["pending"] = ov["pending"].fillna(0).astype(int)
    c = st.columns([2, 2, 1])
    status = c[0].selectbox("Status", ["All", *R.DEPT_STATUSES])
    text = c[1].text_input("Search name")
    official = c[2].checkbox("Official 45 only", value=False)
    f = ov if status == "All" else ov[ov["status"] == status]
    if official:
        f = f[f["official45"] == 1]
    if text:
        f = f[f["name_en"].str.contains(text, case=False) | f["name_hi"].str.contains(text, case=False)]
    show = f[["name_en", "name_hi", "status", "services_mp", "services_mped", "schemes_cmh", "offices", "districts_covered", "tickets", "pending"]]
    st.caption(f"{len(f)} of {len(ov)} departments. Select a row to manage it.")
    ev = ui.table(show, width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key="dept-table")
    rows = ev.selection["rows"]
    if rows:
        st.divider()
        _department_detail(ctx, f.iloc[rows[0]]["id"], editable=True)


def page_my_department(ctx: Context) -> None:
    st.title("My Department")
    if not ctx.account.dept_id:
        st.warning("This account is not linked to a registry department.")
        return
    _department_detail(ctx, ctx.account.dept_id, editable=False)


# --- 3. Geography and coverage ----------------------------------------------------------------------------------

def page_geography(ctx: Context) -> None:
    st.title("Geography and Coverage")
    div = pd.DataFrame(R.rows(ctx.conn, """SELECT d.name AS division, d.std_code,
        (SELECT COUNT(*) FROM districts x WHERE x.division=d.name) AS districts,
        (SELECT SUM(population_2011) FROM districts x WHERE x.division=d.name) AS population_2011 FROM divisions d ORDER BY d.name"""))
    if div.empty:
        st.info("No geography loaded. Run the geography scraper and rebuild the registry (see Data and Sources).")
        return
    st.subheader("Divisions")
    ui.table(div, width="stretch", hide_index=True)
    st.subheader("Districts")
    choice = st.selectbox("Division", ["All"] + list(div["division"]))
    dist = pd.DataFrame(R.rows(ctx.conn, "SELECT name AS district, division, headquarters, std_code, area_sq_km, population_2011, email FROM districts ORDER BY division, name"))
    ui.table(dist if choice == "All" else dist[dist["division"] == choice], width="stretch", hide_index=True)
    st.caption("Source: mpinfo.org (office structure only, no officials' names or numbers).")
    st.subheader("Department coverage by district")
    st.caption("Each cell is the office status for that department in that district. 'not onboarded' means no office is registered, never a guess.")
    sel = st.selectbox("Show districts of", [d for d in div["division"]], key="cov-div")
    districts = list(dist[dist["division"] == sel]["district"])
    matrix = pd.DataFrame(R.coverage_matrix(ctx.conn))
    cells = matrix[["department"] + districts]
    onboarded = int((cells[districts] != "not onboarded").sum().sum())
    st.caption(f"{onboarded} of {cells[districts].size} department-district cells have an office ({len(districts)} districts in {sel}).")
    colour = {"demo": "background-color:#d5dbe3", "unverified": "background-color:#bfd3ea", "verified": "background-color:#0b5cab;color:#fff"}
    ui.table(cells.style.map(lambda v: colour.get(v, "color:#9ca3af")), width="stretch", hide_index=True)


# --- 4. Services ------------------------------------------------------------------------------------------------

def page_services(ctx: Context) -> None:
    st.title("Services")
    st.caption("What citizens can ask the government for, with the legal deadline, fee and documents where the Lok Seva Guarantee portal publishes them.")
    c = st.columns(3)
    if ctx.account.role == "dept_head" and ctx.account.dept_id:
        dept_id = ctx.account.dept_id
        c[0].write(f"Department: **{dept_id}**")
    else:
        opts = {"all": "All departments", **{d[0]: d[1] for d in ALL_DEPARTMENTS}}
        dept_id = c[0].selectbox("Department", list(opts), format_func=opts.get)
    source = c[1].selectbox("Source", ["mpedistrict", "mp.gov.in", "cmhelpline"], help="mpedistrict = legal deadlines + documents")
    text = c[2].text_input("Search title")
    sql, args = "SELECT * FROM services WHERE source=?", [source]
    if dept_id != "all":
        sql, args = sql + " AND dept_id=?", [source, dept_id]
    if text:
        sql, args = sql + " AND title LIKE ?", [*args, f"%{text}%"]
    found = R.rows(ctx.conn, sql + " ORDER BY title LIMIT 500", tuple(args))
    st.caption(f"{len(found)} service(s) (first 500)")
    if not found:
        return
    df = pd.DataFrame(found)
    cols = ["title", "category", "deadline_urban", "deadline_rural", "fee"] if source == "mpedistrict" else ["title", "category", "apply_url"]
    ev = ui.table(df[cols], width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key="svc-table")
    if ev.selection["rows"]:
        s = found[ev.selection["rows"][0]]
        st.subheader(s["title"])
        docs = json.loads(s["documents"] or "[]")
        if docs:
            st.write("**Documents needed:**")
            for i, doc in enumerate(docs, 1):
                st.write(f"{i}. {doc}")
        if s["apply_url"]:
            st.write("**Apply:**", s["apply_url"])
        if s["detail_url"]:
            st.write("**Official page:**", s["detail_url"])


# --- 5. Tickets and routing -------------------------------------------------------------------------------------

def page_tickets(ctx: Context) -> None:
    st.title("Tickets and Routing")
    _badge(ctx)
    if not _need_tickets(ctx):
        return
    df, legacy, acct = ctx.df, ctx.legacy, ctx.account
    if df.empty:
        st.info("No tickets in your scope.")
        return
    opts = {"can_reassign": acct.can_reassign, "allowed_departments": acct.reassign_departments()}
    tabs = ["All tickets", "Review queue"] + (["Map"] if acct.role in ("cm_admin", "evaluator") and not ctx.is_demo else [])
    table = (lambda frame, key, **o: demo_ticket_table(ctx, frame, key)) if ctx.is_demo else legacy._ticket_table
    t = st.tabs(tabs)
    with t[0]:
        c = st.columns(4)
        status = c[0].selectbox("Status", ["All", *sorted(df["status"].unique())])
        depts = c[1].selectbox("Department", ["All", *sorted(df["department"].unique())])
        pool = df if depts == "All" else df[df["department"] == depts]
        office = c[2].selectbox("Office", ["All", *sorted(pool["office_name"].dropna().unique())])
        q = c[3].text_input("Search complaint ID", value=st.session_state.pop("ticket_q", ""))
        f = df if status == "All" else df[df["status"] == status]
        f = f if depts == "All" else f[f["department"] == depts]
        f = f if office == "All" else f[f["office_name"] == office]
        f = f[f["complaint_id"].str.contains(q, case=False, na=False)] if q else f
        if not acct.can_reassign:
            st.caption("Your role can change ticket status but not reassign tickets.")
        table(f, key="cm-all", **opts)
    with t[1]:
        queue = df[df["status"] == "needs_review"]
        if queue.empty:
            st.success("Nothing needs review.")
        else:
            st.caption("Low routing confidence or no matching office: a person decides where these go.")
            table(queue, key="cm-review", **opts)
    if len(t) > 2:
        with t[2]:
            legacy._render_map_tab(df, df)


# --- 6. Routing lab (Jev) ---------------------------------------------------------------------------------------

def jev_route(text: str, key: str, timeout: float = 30.0) -> dict:
    """Ask TypeSafe Jev which of the 49 departments owns this complaint. Returns the raw `dept` answer."""
    criteria = {d[0]: (f"{d[1]}: {ROUTING_HINTS[d[0]]} | {d[2]}" if ROUTING_HINTS.get(d[0]) else f"{d[1]} | {d[2]}") for d in ALL_DEPARTMENTS}
    body = {"model": "jev-latest", "state": text, "questions": {"dept": {
        "type": "choice", "instructions": "Which government department should handle this citizen's complaint or request? The message may be in a Hindi dialect.",
        "criteria": criteria}}}
    r = httpx.post(TYPESAFE_URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()["answers"]["dept"]


def gate(confidence: float) -> str:
    """The S28 tiers: route / reconfirm with the citizen / hand to a person."""
    return "route" if confidence >= 0.8 else "reconfirm" if confidence >= 0.5 else "human_evaluation"


def page_routing_lab(ctx: Context) -> None:
    st.title("Routing Lab")
    st.caption("Type a complaint in any dialect and see which department it would go to among all 49, with confidence. Experimental: uses TypeSafe Jev.")
    st.warning("The text you type is sent to TypeSafe's API (a third party). Type only made-up or already-public text, never a real citizen's details.")
    key = _typesafe_key()
    if not key:
        st.info("Set TYPESAFE_API_KEY in the environment (or local-research/.env) to enable this page.")
        return
    text = st.text_area("Complaint text", "हमाए गाँव में हैंडपंप तीन दिन से खराब है", height=90)
    if st.button("Route it") and text.strip():
        try:
            ans = jev_route(text.strip(), key)
        except (httpx.HTTPError, KeyError) as exc:
            st.error(f"Could not reach the routing model: {exc.__class__.__name__}")
            return
        names = {d[0]: d[1] for d in ALL_DEPARTMENTS}
        top = sorted(ans["probabilities"].items(), key=lambda kv: -kv[1])[:3]
        action = gate(ans["confidence"])
        st.metric("Top department", names[ans["choice"]], f"confidence {ans['confidence']:.2f}")
        st.write({"route": "✅ Confident: create the ticket for this department.", "reconfirm": "❓ Ask the citizen to confirm between the top choices.",
                  "human_evaluation": "🧑 Too uncertain: send to Human Evaluation (a person decides)."}[action])
        ui.table(pd.DataFrame([{"department": names[k], "probability": round(v, 3), "in Samadhan today": _name_for_live(k) or "no"} for k, v in top]),
                     width="stretch", hide_index=True)
        if not _name_for_live(ans["choice"]):
            st.info("Samadhan has no live routing for this department yet: today the ticket would go to Human Evaluation.")


# --- 7. Public flow (scraped portal totals) ---------------------------------------------------------------------

def page_public_flow(ctx: Context) -> None:
    st.title("Public Flow (MP portals)")
    snap = _snapshot()
    if not snap:
        st.info("No snapshot found. Run the mpedistrict scraper (see Data and Sources).")
        return

    def g(name: str) -> dict:
        return next(v for k, v in snap.items() if k.endswith(name))

    chart, fa, sa = g("GetChartData"), g("GetFirstAppealData"), g("GetSecondAppealData")
    st.caption(f"Public totals from mpedistrict.gov.in (Lok Seva Guarantee portal), portal time **{chart.get('reg_datetime', '?')}**. Not Samadhan's data; a snapshot, not live.")
    c = st.columns(4)
    c[0].metric("Applications received", chart["reg_recd"])
    c[1].metric("Disposed", f"{chart['reg_disp']:,}")
    c[2].metric("Pending", f"{chart['reg_pend']:,}")
    c[3].metric("Registered on snapshot day", chart["reg_todayreceive"])
    st.subheader("Escalation: appeals")
    a, b = st.columns(2)
    a.write("**First appeal**")
    a.bar_chart(pd.DataFrame({"count": {"received": fa["fa_recd"], "disposed": fa["fa_disp"], "pending": fa["fa_pend"], "in time": fa["fa_recd_in_time"], "late": fa["fa_recd_late"]}}))
    a.caption(f"{fa['fa_recd_late'] / fa['fa_recd'] * 100:.0f}% of first appeals were late; {fa['fa_auto']} were filed automatically.")
    b.write("**Second appeal**")
    b.bar_chart(pd.DataFrame({"count": {"received": sa["sa_recd"], "disposed": sa["sa_disp"], "pending": sa["sa_pend"], "penalty cases": sa["sa_penalty"]}}))
    b.caption(f"{sa['sa_penalty']} penalty cases imposed on officers; {sa['sa_auto']} filed automatically.")
    st.subheader("Where applications come from")
    k = g("GetKioskWiseRegistrationData")
    st.bar_chart(pd.DataFrame({"applications": {"LSK centres": k["lsk_reg"], "CSC": k["csc_reg"], "eKYC (online)": k["ekyc_reg"], "MPOnline": k["mpo_reg"], "DO office": k["dooffice_reg"]}}))
    o = g("GetCitizenOutreachData")
    st.caption(f"Outreach: {o['lskkioskcnt']} LSK centres, {o['mpokioskcnt']:,} MPOnline and {o['csckioskcnt']:,} CSC kiosks active.")
    trend = g("GetAutoFirstAndSecondAppeal")
    if isinstance(trend, list) and trend:
        st.subheader("Automatic appeals per day")
        st.line_chart(pd.DataFrame(trend).set_index("RegDt")[["FirstAppeal", "SecondAppeal"]].astype(int))


# --- 8. Data and sources ----------------------------------------------------------------------------------------

def page_data(ctx: Context) -> None:
    st.title("Data and Sources")
    files = [("mp.gov.in services", R.DATA_DIR / "mp_gov_services.csv"), ("mpedistrict services", SNAPSHOT_DIR / "services.jsonl"),
             ("mpedistrict live stats", next(iter(sorted(SNAPSHOT_DIR.glob("live_stats_snapshot_*.json"))), SNAPSHOT_DIR / "live_stats_snapshot.json")),
             ("CM Helpline schemes", R.DATA_DIR / "cmhelpline_schemes.csv"), ("Geography (districts)", R.DATA_DIR / "geography" / "districts.csv"),
             ("Registry database", R.DEFAULT_DB)]
    ui.table(pd.DataFrame([{"dataset": n, "file": str(p.relative_to(R.REPO_ROOT)) if p.exists() else f"{p.name} (missing)",
                                "last updated": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if p.exists() else "-"} for n, p in files]),
                 width="stretch", hide_index=True)
    st.subheader("Rebuild the registry")
    st.caption("Reloads the scraped files above and Samadhan's live offices (read-only). Manual edits and the audit log are kept.")
    if st.button("Rebuild registry now"):
        from dashboard.cm.build_cli import fetch_live_offices

        summary = R.build(ctx.conn, live_offices=fetch_live_offices())
        R.audit(ctx.conn, ctx.account.username, "registry.rebuild", "all", json.dumps({k: v for k, v in summary.items() if k != "unmatched_departments"}))
        ctx.conn.commit()
        st.success({k: v for k, v in summary.items() if k != "unmatched_departments"})
    st.subheader("Refresh the scraped data")
    st.code("cd local-research/data\n"
            "python ../scripts/mp_gov_services_scrape.py\n"
            "python ../scripts/mpedistrict_services_scrape.py mpedistrict\n"
            "python ../scripts/geography_scrape.py geography\n"
            "python ../scripts/cmhelpline_schemes_scrape.py      # see README\n"
            "# then press 'Rebuild registry now' above", language="bash")
    st.caption("Scrapers run from the command line on purpose (politeness delays, curl for the old TLS on government servers). Public pages only; officer logins and captcha pages are never touched.")
    st.subheader("Names that could not be matched to a department")
    un = R.rows(ctx.conn, "SELECT source, raw_department, COUNT(*) AS services FROM services WHERE dept_id IS NULL GROUP BY source, raw_department ORDER BY services DESC")
    ui.table(pd.DataFrame(un), width="stretch", hide_index=True) if un else st.success("Every service is linked to a department.")
    st.subheader("Audit log (latest 200)")
    ui.table(pd.DataFrame(R.rows(ctx.conn, "SELECT ts, actor, action, target, detail FROM audit_log ORDER BY id DESC LIMIT 200")), width="stretch", hide_index=True)


# --- 9. Accounts ------------------------------------------------------------------------------------------------

def page_accounts(ctx: Context) -> None:
    from dashboard.cm.accounts import load_accounts

    st.title("Accounts and Roles")
    st.info("Demo accounts. Scoping is enforced by this app only, because the dashboard talks to Supabase with the service key (which bypasses "
            "row-level security). Real separation needs Supabase Auth and row-level security per department.")
    accts = load_accounts()
    if accts:
        ui.table(pd.DataFrame([{"username": a["username"], "role": a["role"], "department": a.get("department", ""), "office": a.get("office_name", ""),
                                    "description": a.get("label", "")} for a in accts]), width="stretch", hide_index=True)
    else:
        st.warning("No accounts file. Create demo accounts: `uv run python -m dashboard.cm.make_demo_accounts`")
    st.write("**Roles**")
    st.markdown("- **cm_admin**: everything, including this page.\n- **dept_head**: one department's tickets and page; can reassign only inside the department.\n"
                "- **office_officer**: one office's tickets; can change status, cannot reassign.\n- **evaluator**: the Human Evaluation queue plus every ticket needing review; can reassign to any department.")
    st.caption("Plain-text demo passwords are in local-research/DEMO_ACCOUNTS.md (git-excluded).")
    from dashboard.cm.pages_access import desk_access_section

    desk_access_section(ctx)


from dashboard.cm.pages_eval import page_human_eval  # noqa: E402,F401
from dashboard.cm.pages_extra import demo_ticket_table, page_area, page_search  # noqa: E402,F401
