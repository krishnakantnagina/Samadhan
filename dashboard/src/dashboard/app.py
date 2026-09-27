"""S13 -- Officer Dashboard entry point (T23): password gate, ticket list, filters.
Spec: docs/specs/S13-dashboard-auth-list.md.

Run: uv run streamlit run src/dashboard/app.py (from dashboard/).
"""

import secrets

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from dashboard.config import get_dashboard_config
from dashboard.tickets import list_tickets

load_dotenv()  # repo-root .env -- Streamlit does not auto-load it (S13 plan step S10)

st.set_page_config(page_title="Samadhan — Officer Dashboard", layout="wide")


@st.cache_data(ttl=30)
def _cached_tickets() -> pd.DataFrame:
    """One fetch serves every filter combination for 30s (S13 BEHAVIOR 2) -- filtering below is
    in-memory, not a query per filter."""
    rows = list_tickets()
    df = pd.json_normalize(rows)
    return df.rename(columns={"offices.office_name": "office_name", "offices.level": "office_level"})


def _require_login() -> None:
    if st.session_state.get("authenticated"):
        return
    st.title("Samadhan — Officer Dashboard")
    password = st.text_input("Password", type="password")
    if st.button("Log in"):
        config = get_dashboard_config()  # raises at startup if DASHBOARD_PASSWORD is unset
        if secrets.compare_digest(password, config.dashboard_password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()


def main() -> None:
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

    st.title("Tickets")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        statuses = st.multiselect(
            "Status", sorted(df["status"].unique()), default=list(df["status"].unique())
        )
    with col2:
        departments = ["All"] + sorted(df["department"].unique())
        department = st.selectbox("Department", departments)
    with col3:
        office_pool = df if department == "All" else df[df["department"] == department]
        offices = ["All"] + sorted(office_pool["office_name"].dropna().unique())
        office = st.selectbox("Office", offices)
    with col4:
        search = st.text_input("Search complaint ID")

    filtered = df[df["status"].isin(statuses)]
    if department != "All":
        filtered = filtered[filtered["department"] == department]
    if office != "All":
        filtered = filtered[filtered["office_name"] == office]
    if search:
        filtered = filtered[filtered["complaint_id"].str.contains(search, case=False, na=False)]

    review_count = int((filtered["status"] == "needs_review").sum())
    if review_count:
        st.warning(f"{review_count} ticket(s) need review.")

    st.dataframe(
        filtered[
            [
                "complaint_id",
                "status",
                "department",
                "office_name",
                "summary_en",
                "created_at",
                "updated_at",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


if __name__ == "__main__":
    main()
