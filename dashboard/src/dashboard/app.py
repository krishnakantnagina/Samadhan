"""S13 -- Officer Dashboard entry point (T23): password gate, ticket list, filters.
S14 -- detail panel, status change, reassign, review queue (T24).
Spec: docs/specs/S13-dashboard-auth-list.md, docs/specs/S14-dashboard-detail-actions.md.

Run: uv run streamlit run src/dashboard/app.py (from dashboard/).
"""

import secrets

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from dashboard.analytics import DEFAULT_SLA_DAYS, ageing, daily_received_resolved, department_summary, totals
from dashboard.cm import charts, theme, ui
from dashboard.cm.ui import table as ui_table
from dashboard.config import get_dashboard_config
from dashboard.db import get_client
from dashboard.gov_catalogue import department_coverage, load_services
from dashboard.labels import display_field, intake_notes
from dashboard.safe import md, tel_link
from dashboard.throttle import LOGIN_THROTTLE, locked_message
from dashboard.table_state import selected_row, table_key
from dashboard.map_view import build_map, issue_label, legend_markdown, office_name, split_points
from dashboard.tickets import (
    ReassignError,
    get_ticket_detail,
    count_tickets,
    list_all_offices,
    list_events,
    list_map_points,
    list_routing_corrections,
    list_tickets,
    reassign_ticket,
    record_event,
    truncation_notice,
    update_status,
)

load_dotenv()  # repo-root .env -- Streamlit does not auto-load it

STATUSES = ["new", "in_progress", "resolved", "needs_review"]


@st.cache_data(ttl=30)
def _cached_tickets() -> pd.DataFrame:
    """One fetch serves every filter combination for 30s (S13 BEHAVIOR 2) -- filtering below is
    in-memory, not a query per filter. Cleared explicitly after any write (S14) so a status change
    or reassign shows up immediately, not after a stale 30s wait."""
    rows = list_tickets()
    df = pd.json_normalize(rows)
    return df.rename(columns={"offices.office_name": "office_name", "offices.level": "office_level"})


@st.cache_data(ttl=30)
def _cached_ticket_count() -> int | None:
    return count_tickets()


@st.cache_data(ttl=30)
def _cached_map_points() -> list[dict]:
    """Same 30 s cache, cleared after writes like the ticket list (S24 section 4)."""
    return list_map_points()


def _render_map_tab(df: pd.DataFrame, filtered: pd.DataFrame) -> None:
    """S24: exact-GPS pins for the tickets the All Tickets filters currently show; the rest are
    counted and listed, never faked onto the map."""
    st.title("Map")
    visible_ids = set(filtered["complaint_id"])
    rows = [r for r in _cached_map_points() if r["complaint_id"] in visible_ids]
    with_gps, without_gps = split_points(rows)

    if not with_gps:
        st.info("No tickets with a GPS location match the current filters.")
    else:
        st.markdown(legend_markdown(), unsafe_allow_html=True)
        try:
            st_folium(build_map(with_gps), height=460, use_container_width=True, returned_objects=[])
        except Exception as exc:  # noqa: BLE001 -- a map failure must not break the other tabs
            st.error(f"Could not draw the map: {exc}")
        st.caption(f"{len(with_gps)} ticket(s) on the map.")

    if without_gps:
        st.warning(f"{len(without_gps)} ticket(s) have no GPS and are not on the map.")
        with st.expander("Tickets without GPS"):
            ui_table(
                pd.DataFrame(
                    {
                        "complaint_id": [r["complaint_id"] for r in without_gps],
                        "status": [r["status"] for r in without_gps],
                        "issue": [issue_label(r) for r in without_gps],
                        "location given": [
                            (r.get("fields") or {}).get("location", "-") for r in without_gps
                        ],
                        "office": [office_name(r) for r in without_gps],
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    if with_gps:
        st.divider()
        options = [r["complaint_id"] for r in with_gps]
        chosen = st.selectbox("Open ticket", ["-", *options], key="map-open-ticket")
        if chosen != "-":
            _render_detail(df[df["complaint_id"] == chosen].iloc[0], "map")


def _render_department_counts(df: pd.DataFrame) -> None:
    """S28 4.4 Phase A: how many tickets each department has waiting (new + needs review)."""
    waiting = df[df["status"].isin(["new", "needs_review"])].groupby("department").size()
    departments = sorted(df["department"].unique())
    columns = st.columns(len(departments))
    for column, department in zip(columns, departments, strict=True):
        column.metric(department, int(waiting.get(department, 0)), help="new + needs review")


def _render_overview_tab(df: pd.DataFrame) -> None:
    """State -> department view: KPI tiles, department league table, ageing, 30-day trend.
    Same four numbers (received / resolved / pending / overdue) at every level, like CPGRAMS."""
    st.title("Overview")
    sla_days = st.number_input(
        "Overdue after (days)", min_value=1, max_value=90, value=DEFAULT_SLA_DAYS,
        help="21 days is CPGRAMS's national resolution time. MP Lok Seva Guarantee deadlines vary per service.",
    )
    now = pd.Timestamp.now(tz="UTC")
    summary = department_summary(df, now, sla_days)
    kpi = totals(summary)
    rr = daily_received_resolved(df, now)

    st.markdown(ui.kpi_cards([
        {"label": "Received", "value": f"{kpi['received']:,}", "icon": charts.ICON_INBOX, "spark": rr["received"].tail(14).tolist(), "color": theme.BLUE},
        {"label": "Resolved", "value": f"{kpi['resolved']:,}", "icon": charts.ICON_CHECK, "spark": rr["resolved"].tail(14).tolist(), "color": theme.NAVY, "delta": f"{kpi['resolution_rate']}% rate"},
        {"label": "Pending", "value": f"{kpi['pending']:,}", "icon": charts.ICON_CLOCK},
        {"label": f"Overdue > {sla_days}d", "value": f"{kpi['overdue']:,}", "icon": charts.ICON_ALERT, "delta": "needs follow-up" if kpi["overdue"] else "on track"},
    ]), unsafe_allow_html=True)

    c_trend, c_donut = st.columns([1.7, 1])
    with c_trend:
        st.subheader("Received vs resolved · 30 days")
        st.altair_chart(charts.trend_chart(df, now), use_container_width=True)
    with c_donut:
        st.subheader("Open by department")
        if (summary["pending"] > 0).any():
            st.altair_chart(charts.donut_open_by_dept(summary), use_container_width=True)
        else:
            st.caption("Nothing pending — all clear.")

    st.subheader("Departments")
    st.caption("Most overdue first. Click a department in the All Tickets tab to work its tickets.")
    ui_table(summary, use_container_width=True, hide_index=True)

    st.subheader("Pending by age")
    st.bar_chart(ageing(df, now).set_index("age"), color=theme.BLUE)


def _render_structure_tab(df: pd.DataFrame) -> None:
    """Which MP departments exist and which ones Samadhan handles. Needs local-research/ data."""
    st.title("Govt Structure")
    services = load_services()
    if services is None:
        st.info(
            "The MP service catalogue is not on this machine. Put the `local-research/` folder in the repo "
            "root (it is git-excluded and shared by hand) to see all 45 departments and 2,070 services."
        )
        return
    coverage = department_coverage(services, set(df["department"].unique()))
    a, b, c = st.columns(3)
    a.metric("Departments in catalogue", len(coverage))
    b.metric("Services in catalogue", len(services))
    c.metric("Handled by Samadhan", int((coverage["samadhan_status"] == "live").sum()))
    st.caption("Source: mp.gov.in/services. Department names are Hindi there, so 'live' only matches exact names.")
    ui_table(coverage, use_container_width=True, hide_index=True)

    st.subheader("Search services")
    q1, q2 = st.columns(2)
    dept = q1.selectbox("Department", ["All", *sorted(coverage["department"])], key="catalogue-dept")
    text = q2.text_input("Search title", key="catalogue-text")
    found = services if dept == "All" else services[services["department"] == dept]
    if text:
        found = found[found["title"].str.contains(text, case=False, na=False)]
    st.caption(f"{len(found)} service(s)")
    ui_table(found, use_container_width=True, hide_index=True)


def _actor() -> str:
    """Who is acting, for the audit trail: the signed-in CM-office account, else the shared officer login."""
    account = st.session_state.get("cm_account")
    return account.username if account is not None else ("officer" if st.session_state.get("authenticated") else "unknown")


def _audit_once(complaint_id: str, action: str, detail: str | None = None) -> None:
    """Record a view once per browser session and ticket (Streamlit reruns the page on every click, which would flood the trail)."""
    seen = st.session_state.setdefault("audited_views", set())
    if (complaint_id, action) not in seen:
        seen.add((complaint_id, action))
        record_event(complaint_id, _actor(), action, detail)


def _require_login() -> None:
    if st.session_state.get("authenticated"):
        return
    st.title("Samadhan — Officer Dashboard")
    password = st.text_input("Password", type="password")
    if st.button("Log in"):
        wait = LOGIN_THROTTLE.seconds_locked("officer")
        if wait:
            st.error(locked_message(wait))
            st.stop()
        config = get_dashboard_config()  # raises at startup if DASHBOARD_PASSWORD is unset
        if secrets.compare_digest(password.encode(), config.dashboard_password.encode()):
            LOGIN_THROTTLE.record_success("officer")
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            LOGIN_THROTTLE.record_failure("officer")
            st.error("Wrong password.")
    st.stop()


def _render_audio(audio_path: str) -> None:
    """Signed URL, 300s (G-T06-2) -- long enough for an officer to listen, not a lingering link.
    Never exercised against a real audio file yet (G-S14-1): no ticket has one until T26 ships."""
    try:
        signed = get_client().storage.from_("audio").create_signed_url(path=audio_path, expires_in=300)
        st.audio(signed["signedURL"])
    except Exception as exc:  # noqa: BLE001 -- a bad/missing audio file must not break the panel
        st.warning(f"Could not load audio: {type(exc).__name__}")


def _render_detail(
    row: pd.Series, source: str, *, can_reassign: bool = True, allowed_departments: set[str] | None = None
) -> None:
    """Everything S13's list view deliberately left out, for one deliberately opened ticket
    (S14 BEHAVIOR 2) -- fields, original text, status/reassign forms, reassignment history.

    CM-office roles (dashboard/cm/accounts.py): `can_reassign=False` hides the reassign form, and
    `allowed_departments` limits which departments a ticket may be reassigned TO (None = any).

    `source` names the tab that opened it and prefixes every widget key: Streamlit runs all tabs on
    every rerun, so the same ticket opened from two tabs would otherwise collide (S24 review)."""
    detail = get_ticket_detail(row["complaint_id"])
    if detail is None:
        st.warning("This ticket could not be loaded.")
        return

    st.subheader(detail["complaint_id"])
    _audit_once(detail["complaint_id"], "viewed_ticket")

    for name, value in (detail["fields"] or {}).items():
        if name.startswith("_"):  # internal notes (S30), shown below
            continue
        label, display = display_field(name, value, detail.get("service_id"))
        st.write(f"**{label}:** {md(display)}")
    notes = intake_notes((detail["fields"] or {}).get("_intake"))
    if notes:
        with st.expander("AI intake notes (why this ticket is here)", expanded=detail["status"] == "needs_review"):
            for line in notes:
                st.write(line)
    if detail["lat"] is not None:
        st.write(f"**GPS:** {detail['lat']}, {detail['lng']}")
    phone = (detail.get("users") or {}).get("phone")
    if phone:  # S31: the registered citizen; the officer handling this ticket calls back on this number
        _audit_once(detail["complaint_id"], "viewed_phone")  # who looked at a citizen's number is on record
        st.markdown(f"**📞 Citizen phone (call back):** {tel_link(phone) or md(phone)}")
    place = [f"district {md(detail['district'])}" if detail.get("district") else None, f"tehsil {md(detail['tehsil'])}" if detail.get("tehsil") else None,
             f"near {md(detail['nearest_place'])}" if detail.get("nearest_place") else None]
    if any(place) or detail.get("location_precision"):
        st.write("**Area:** " + (", ".join(p for p in place if p) or "not given") + (f"  ·  precision: {md(detail['location_precision'])}" if detail.get("location_precision") else ""))
    st.write(f"**Original message:** {md(detail['original_text'])}")
    st.write(f"**Routing confidence:** {detail['routing_confidence']}")

    if detail["audio_path"]:
        _render_audio(detail["audio_path"])

    ticket_id = detail["id"]
    key_prefix = f"{source}-{ticket_id}"

    st.divider()
    new_status = st.selectbox(
        "Status", STATUSES, index=STATUSES.index(detail["status"]), key=f"status-{key_prefix}"
    )
    if st.button("Save status", key=f"save-status-{key_prefix}"):
        update_status(detail["complaint_id"], new_status, actor=_actor(), previous=detail["status"])  # S14 RULES 1: only tickets.status
        st.cache_data.clear()
        st.success("Status updated.")
        st.rerun()

    offices = list_all_offices()  # every department (S28 4.4): a wrong department is fixed here
    office_lookup = {o["id"]: o["office_name"] for o in offices}
    options = {
        o["id"]: f"{o['department']}: {o['office_name']}"
        for o in offices
        if o["id"] != detail["office_id"]
        and (allowed_departments is None or o["department"] in allowed_departments)
    }
    if options and can_reassign:
        to_office_id = st.selectbox(
            "Reassign to",
            list(options),
            format_func=lambda i: options[i],
            key=f"office-{key_prefix}",
        )
        reason = st.text_input("Reason (optional)", key=f"reason-{key_prefix}")
        if st.button("Reassign", key=f"reassign-{key_prefix}"):
            try:
                reassign_ticket(
                    ticket_id=ticket_id,
                    from_office_id=detail["office_id"],
                    to_office_id=to_office_id,
                    reason=reason or None,
                    actor=_actor(),
                    complaint_id=detail["complaint_id"],
                )
            except ReassignError as exc:
                st.error(str(exc))  # S02 ERRORS: reassign to same office -> rejected
            else:
                st.cache_data.clear()
                st.success("Reassigned.")
                st.rerun()

    events = list_events(detail["complaint_id"])
    if events:
        with st.expander(f"Activity on this ticket ({len(events)})"):
            for e in events:
                st.write(f"- {md(e['created_at'])}: **{md(e['actor'])}** {md(e['action'])}" + (f" ({md(e['detail'])})" if e.get("detail") else ""))

    corrections = list_routing_corrections(ticket_id)
    if corrections:
        st.write("**Reassignment history:**")
        for c in corrections:
            from_name = office_lookup.get(c["from_office_id"], f"#{c['from_office_id']}")
            to_name = office_lookup.get(c["to_office_id"], f"#{c['to_office_id']}")
            note = f" — {md(c['reason'])}" if c["reason"] else ""
            st.write(f"- {c['created_at']}: {md(from_name)} → {md(to_name)}{note}")


def _ticket_table(df: pd.DataFrame, *, key: str, **detail_options) -> None:
    display_cols = [
        "complaint_id", "status", "department", "office_name", "summary_en", "created_at", "updated_at",
    ]
    widget_key = table_key(key, df)  # a changed list drops any stale selection (see table_state.py)
    event = ui_table(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=widget_key,
    )
    row = selected_row(df, event.selection["rows"])
    if row is not None:
        st.divider()
        _render_detail(row, key, **detail_options)


def main() -> None:
    st.set_page_config(page_title="Samadhan — Officer Dashboard", layout="wide")  # inside main() so cm_app can import this module
    theme.inject()  # government blue theme + KPI-card styling (cm_app injects its own; this is for running app.py standalone)
    _require_login()

    with st.sidebar:
        st.button("Log out", on_click=lambda: st.session_state.pop("authenticated", None))

    try:
        df = _cached_tickets()
    except Exception as exc:  # noqa: BLE001 -- a transient DB hiccup should not crash the app
        st.error(f"Could not load tickets: {exc}")
        return

    if df.empty:
        st.info("No tickets yet.")
        return

    notice = truncation_notice(len(df), _cached_ticket_count())
    if notice:
        st.warning(notice)

    _render_department_counts(df)

    tab_overview, tab_all, tab_review, tab_map, tab_structure = st.tabs(
        ["Overview", "All Tickets", "Review Queue", "Map", "Govt Structure"]
    )

    with tab_overview:
        _render_overview_tab(df)

    with tab_structure:
        _render_structure_tab(df)

    with tab_all:
        st.title("Tickets")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            status = st.selectbox("Status", ["All", *sorted(df["status"].unique())])
        with col2:
            departments = ["All"] + sorted(df["department"].unique())
            department = st.selectbox("Department", departments)
        with col3:
            office_pool = df if department == "All" else df[df["department"] == department]
            offices = ["All"] + sorted(office_pool["office_name"].dropna().unique())
            office = st.selectbox("Office", offices)
        with col4:
            search = st.text_input("Search complaint ID")

        filtered = df if status == "All" else df[df["status"] == status]
        if department != "All":
            filtered = filtered[filtered["department"] == department]
        if office != "All":
            filtered = filtered[filtered["office_name"] == office]
        if search:
            filtered = filtered[filtered["complaint_id"].str.contains(search, case=False, na=False)]

        review_count = int((filtered["status"] == "needs_review").sum())
        if review_count:
            st.warning(f"{review_count} ticket(s) need review.")

        _ticket_table(filtered, key="all-tickets")

    with tab_review:
        st.title("Review Queue")
        queue = df[df["status"] == "needs_review"]
        if queue.empty:
            st.success("Nothing needs review.")
        else:
            _ticket_table(queue, key="review-queue")

    with tab_map:
        _render_map_tab(df, filtered)


if __name__ == "__main__":
    main()
