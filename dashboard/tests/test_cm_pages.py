"""Smoke tests: every CM-office page opens, for every role allowed to see it, with no exception. Uses a temporary registry and a stub
for the legacy ticket table/map (which would call Supabase), so it needs neither the database nor the scraped files."""

import os

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from dashboard.cm import accounts, registry as R
from dashboard.cm.pages import gate

LIVE = [{"id": 1, "department": "Jal Vibhag", "level": "district", "name": "Bhopal", "office_name": "BMC Head Office", "active": True},
        {"id": 2, "department": "Human Evaluation", "level": "district", "name": "Bhopal", "office_name": "Desk", "active": True}]


def _script():
    import os

    import pandas as pd
    import streamlit as st

    from dashboard.cm import accounts, pages, registry

    class Legacy:  # stands in for dashboard.app (Supabase-backed)
        @staticmethod
        def _ticket_table(df, *, key, **opts):
            st.write(f"TICKET TABLE {len(df)} rows opts={opts}")

        @staticmethod
        def _render_map_tab(df, filtered):
            st.write("MAP")

    now = pd.Timestamp.now(tz="UTC")
    df = pd.DataFrame({
        "complaint_id": ["SMD-1", "SMD-2", "SMD-3"], "status": ["new", "needs_review", "resolved"],
        "department": ["Jal Vibhag", "Human Evaluation", "Jal Vibhag"], "office_name": ["BMC Head Office", "Desk", "BMC Head Office"],
        "summary_en": ["a", "b", "c"], "created_at": [(now - pd.Timedelta(days=d)).isoformat() for d in (30, 4, 6)],
        "updated_at": [(now - pd.Timedelta(days=d)).isoformat() for d in (30, 4, 5)],
    })
    role = os.environ["CM_TEST_ROLE"]
    demo = os.environ.get("CM_TEST_DEMO") == "1"
    if demo:
        from dashboard.cm import demo_data

        ds = [{"name": n, "division": d, "population_2011": p} for n, d, p in [("Bhopal", "Bhopal", 2371061), ("Sagar", "Sagar", 2378295), ("Rewa", "Rewa", 2363744),
                                                                              ("Indore", "Indore", 3276697), ("Dindori", "Jabalpur", 704218)]]
        names = {d[0]: d[1] for d in __import__("dashboard.cm.departments", fromlist=["ALL_DEPARTMENTS"]).ALL_DEPARTMENTS}
        df = demo_data.generate(ds, names, n=120, seed=1)
        st.session_state["demo_df"] = df.copy()
    acct = {"cm_admin": accounts.Account("a", "cm_admin"),
            "dept_head": accounts.Account("h", "dept_head", department="Jal Vibhag", dept_id="phe"),
            "office_officer": accounts.Account("o", "office_officer", department="Jal Vibhag", office_name="BMC Head Office", dept_id="phe"),
            "evaluator": accounts.Account("t", "evaluator")}[role]
    ctx = pages.Context(acct, registry.connect(os.environ["CM_TEST_DB"]), accounts.scope_tickets(df, acct), None, Legacy, is_demo=demo)
    getattr(pages, os.environ["CM_TEST_PAGE"])(ctx)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "r.db"
    conn = R.connect(path)
    R.build(conn, tmp_path / "nodata", LIVE)
    conn.close()
    monkeypatch.setenv("CM_TEST_DB", str(path))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    return path


PAGES = {"search": "page_search", "area": "page_area", "command": "page_command", "departments": "page_departments", "my_department": "page_my_department", "geography": "page_geography",
         "services": "page_services", "tickets": "page_tickets", "routing_lab": "page_routing_lab", "public_flow": "page_public_flow",
         "data": "page_data", "accounts": "page_accounts"}


@pytest.mark.parametrize("role", accounts.ROLES)
def test_every_allowed_page_opens_for_every_role(db, monkeypatch, role):
    for key, fn in PAGES.items():
        if role not in accounts.PAGE_ACCESS[key]:
            continue
        monkeypatch.setenv("CM_TEST_ROLE", role)
        monkeypatch.setenv("CM_TEST_PAGE", fn)
        at = AppTest.from_function(_script, default_timeout=60).run()
        assert not at.exception, f"{key} as {role}: {[e.value for e in at.exception]}"


def test_dept_head_ticket_page_is_scoped_and_reassign_limited(db, monkeypatch):
    monkeypatch.setenv("CM_TEST_ROLE", "dept_head")
    monkeypatch.setenv("CM_TEST_PAGE", "page_tickets")
    at = AppTest.from_function(_script, default_timeout=60).run()
    text = " ".join(m.value for m in at.markdown)
    assert "TICKET TABLE 2 rows" in text  # Jal Vibhag only: the Human Evaluation ticket is hidden
    assert "allowed_departments': {'Jal Vibhag'}" in text and "can_reassign': True" in text


def test_office_officer_cannot_reassign(db, monkeypatch):
    monkeypatch.setenv("CM_TEST_ROLE", "office_officer")
    monkeypatch.setenv("CM_TEST_PAGE", "page_tickets")
    text = " ".join(m.value for m in AppTest.from_function(_script, default_timeout=60).run().markdown)
    assert "can_reassign': False" in text


def test_confidence_gate_matches_s28_tiers():
    assert gate(0.95) == "route" and gate(0.8) == "route"
    assert gate(0.79) == "reconfirm" and gate(0.5) == "reconfirm"
    assert gate(0.49) == "human_evaluation"


def test_routing_lab_asks_for_a_key_when_missing(db, monkeypatch):
    monkeypatch.setenv("CM_TEST_ROLE", "cm_admin")
    monkeypatch.setenv("CM_TEST_PAGE", "page_routing_lab")
    monkeypatch.setattr("dashboard.cm.pages._typesafe_key", lambda: None, raising=False)
    at = AppTest.from_function(_script, default_timeout=60).run()
    assert not at.exception
    assert os.environ.get("TYPESAFE_API_KEY") is None


@pytest.mark.parametrize("role", ["cm_admin", "dept_head"])
def test_area_page_works_on_demo_data(db, monkeypatch, role):
    R.connect(db).executescript("INSERT OR IGNORE INTO districts (name, division, population_2011) VALUES ('Bhopal','Bhopal',2371061),('Sagar','Sagar',2378295),"
                                "('Rewa','Rewa',2363744),('Indore','Indore',3276697),('Dindori','Jabalpur',704218);")
    monkeypatch.setenv("CM_TEST_ROLE", role)
    monkeypatch.setenv("CM_TEST_PAGE", "page_area")
    monkeypatch.setenv("CM_TEST_DEMO", "1")
    at = AppTest.from_function(_script, default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(m.label == "Districts with complaints" for m in at.metric)
    assert any("DEMO DATA" in m.value for m in at.markdown)  # the demo badge is always visible


def test_demo_tickets_page_is_scoped_for_a_department_head(db, monkeypatch):
    monkeypatch.setenv("CM_TEST_ROLE", "dept_head")
    monkeypatch.setenv("CM_TEST_PAGE", "page_tickets")
    monkeypatch.setenv("CM_TEST_DEMO", "1")
    at = AppTest.from_function(_script, default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    shown = pd.concat([d.value for d in at.dataframe if "DEPARTMENT" in d.value])  # column names are shown in CAPITALS
    assert set(shown["DEPARTMENT"]) == {"Jal Vibhag"}  # never another department's tickets


def test_search_page_finds_a_department_in_english_and_hindi(db, monkeypatch):
    monkeypatch.setenv("CM_TEST_ROLE", "cm_admin")
    monkeypatch.setenv("CM_TEST_PAGE", "page_search")
    for q in ("energy", "ऊर्जा", "bijli"):
        at = AppTest.from_function(_script, default_timeout=60)
        at.session_state["global_q"] = q
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
        assert "Energy" in text, q


def test_search_hides_other_departments_from_a_department_head(db, monkeypatch):
    monkeypatch.setenv("CM_TEST_ROLE", "dept_head")  # Jal Vibhag head (phe): may not find the Energy department
    monkeypatch.setenv("CM_TEST_PAGE", "page_search")
    at = AppTest.from_function(_script, default_timeout=60)
    at.session_state["global_q"] = "energy"
    at.run()
    assert not at.exception
    assert "Energy" not in " ".join(m.value for m in at.markdown)


def _tickets_at(monkeypatch, role="cm_admin"):
    monkeypatch.setenv("CM_TEST_ROLE", role)
    monkeypatch.setenv("CM_TEST_PAGE", "page_tickets")
    monkeypatch.setenv("CM_TEST_DEMO", "1")
    return AppTest.from_function(_script, default_timeout=90).run()


def _shown(at):
    """The ticket list the filters control: the FIRST ticket table on the page (the second is the Review queue tab, which always shows needs_review)."""
    return next(d.value for d in at.dataframe if "STATUS" in d.value and "DEPARTMENT" in d.value)


def test_status_filter_selects_one_status_at_a_time(db, monkeypatch):
    at = _tickets_at(monkeypatch)
    status = next(s for s in at.selectbox if s.label == "Status")  # a single select, not a multiselect
    assert status.options[0] == "All" and not [m for m in at.multiselect if m.label == "Status"]
    assert set(_shown(at)["STATUS"]) > {"resolved"}  # All: several statuses visible
    status.select("resolved").run()
    assert set(_shown(at)["STATUS"]) == {"resolved"}


def test_department_filter_selects_one_department_at_a_time(db, monkeypatch):
    at = _tickets_at(monkeypatch)
    dept = next(s for s in at.selectbox if s.label == "Department")
    assert dept.options[0] == "All" and not [m for m in at.multiselect if m.label == "Department"]
    dept.select("Jal Vibhag").run()
    assert set(_shown(at)["DEPARTMENT"]) == {"Jal Vibhag"}
    status = next(s for s in at.selectbox if s.label == "Status")
    status.select("resolved").run()  # both filters at once
    rows = _shown(at)
    assert set(rows["DEPARTMENT"]) == {"Jal Vibhag"} and set(rows["STATUS"]) == {"resolved"}
