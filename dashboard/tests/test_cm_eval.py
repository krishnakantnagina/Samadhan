from datetime import UTC, datetime

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from dashboard.cm import accounts, demo_data, pages_eval
from dashboard.cm import registry as R
from dashboard.cm.departments import ALL_DEPARTMENTS

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
DISTRICTS = [{"name": n, "division": d, "population_2011": 1_000_000} for n, d in [("Sagar", "Sagar"), ("Rewa", "Rewa"), ("Indore", "Indore"), ("Dindori", "Jabalpur"),
                                                                                 ("Chhatarpur", "Sagar"), ("Shivpuri", "Gwalior"), ("Bhopal", "Bhopal")]]
NAMES = {d[0]: d[1] for d in ALL_DEPARTMENTS}


def demo(n=360):
    return demo_data.generate(DISTRICTS, NAMES, n=n, seed=5, now=NOW)


def test_demo_human_evaluation_fields_are_consistent():
    df = demo()
    queue = df[df["status"] == "needs_review"]
    assert len(queue) > 0 and (queue["eval_reason"] != "").all()  # waiting means there is a reason
    assert set(df["eval_reason"]) <= {"", "department_unconfirmed", "location_unclear", "vague_description"}
    triage = queue[queue["department"] == "Human Evaluation"]
    assert (triage["eval_reason"] == "department_unconfirmed").all()  # only an unconfirmed department sits at the triage desk
    assert (df["jev_top_p"] + df["jev_second_p"] <= 1.011).all() and (df["jev_top_p"] <= 1).all()
    assert (queue.loc[queue["eval_reason"] == "department_unconfirmed", "jev_top_p"] < 0.65).all()  # genuinely unsure
    done = df[df["evaluated_by"] != ""]
    assert len(done) > 10 and (done["status"] != "needs_review").all() and (done["evaluated_dept"] != "").all()
    assert df["citizen_message"].str.len().min() > 5 and (df["questions_asked"].between(0, 3)).all()


def test_insights_counts_agreement_and_confused_pairs():
    now = NOW.isoformat()
    rows = [  # 2 waiting, 3 decided (2 kept Jev's first choice)
        dict(status="needs_review", created_at=now, questions_asked=1, jev_top="School Education", jev_second="Higher Education", department="Human Evaluation", evaluated_by=""),
        dict(status="needs_review", created_at=now, questions_asked=2, jev_top="School Education", jev_second="Higher Education", department="Human Evaluation", evaluated_by=""),
        dict(status="new", created_at=now, questions_asked=1, jev_top="Energy", jev_second="Finance", department="Energy", evaluated_by="evaluator.desk"),
        dict(status="new", created_at=now, questions_asked=1, jev_top="Home", jev_second="Finance", department="Home", evaluated_by="evaluator.desk"),
        dict(status="new", created_at=now, questions_asked=1, jev_top="Higher Education", jev_second="School Education", department="School Education", evaluated_by="evaluator.desk"),
    ]
    info = pages_eval.insights(pd.DataFrame(rows))
    assert (info["waiting"], info["evaluated"], info["agree_pct"], info["avg_questions"]) == (2, 3, 66.7, 1.5)
    top = info["confused"].iloc[0]
    assert top["pair"] == "Higher Education vs School Education" and top["times"] == 3  # 2 waiting + 1 overruled


def test_a_human_decision_assigns_the_department_and_records_who_and_why():
    store = demo().copy()
    cid = store.loc[store["status"] == "needs_review", "complaint_id"].iloc[0]
    others_before = store[store["complaint_id"] != cid].copy()
    pages_eval._decide(store, cid, "School Education", "evaluator.desk", "student is in class 9")
    r = store[store["complaint_id"] == cid].iloc[0]
    assert (r["status"], r["department"], r["evaluated_by"], r["evaluated_dept"], r["eval_note"]) == ("new", "School Education", "evaluator.desk", "School Education", "student is in class 9")
    assert "School Education office" in r["office_name"]
    pd.testing.assert_frame_equal(store[store["complaint_id"] != cid].drop(columns=["eval_note"], errors="ignore").reset_index(drop=True), others_before.drop(columns=["eval_note"], errors="ignore").reset_index(drop=True))


def test_not_a_grievance_closes_the_ticket_without_a_department():
    store = demo().copy()
    cid = store.loc[store["status"] == "needs_review", "complaint_id"].iloc[0]
    pages_eval._decide(store, cid, None, "evaluator.desk", "just a greeting")
    r = store[store["complaint_id"] == cid].iloc[0]
    assert (r["status"], r["evaluated_dept"]) == ("resolved", "(not a grievance)")


def test_only_cm_office_and_triage_may_open_the_page():
    assert accounts.Account("a", "cm_admin").can_open("human_eval") and accounts.Account("t", "evaluator").can_open("human_eval")
    assert not accounts.Account("h", "dept_head", department="Jal Vibhag").can_open("human_eval")
    assert not accounts.Account("o", "office_officer", department="Jal Vibhag", office_name="x").can_open("human_eval")


def _script():
    import os

    import pandas as pd
    import streamlit as st

    from dashboard.cm import accounts, demo_data, pages, registry
    from dashboard.cm.departments import ALL_DEPARTMENTS

    class Legacy:
        @staticmethod
        def _ticket_table(df, *, key, **opts):
            st.write(f"LIVE QUEUE {len(df)}")

    ds = [{"name": n, "division": d, "population_2011": 1_000_000} for n, d in [("Sagar", "Sagar"), ("Rewa", "Rewa"), ("Indore", "Indore"), ("Bhopal", "Bhopal")]]
    names = {d[0]: d[1] for d in ALL_DEPARTMENTS}
    live = os.environ.get("CM_EVAL_LIVE") == "1"
    df = demo_data.generate(ds, names, n=150, seed=3)
    if live:
        df = df[["complaint_id", "status", "department", "office_name", "created_at", "updated_at", "summary_en"]]
    else:
        st.session_state["demo_df"] = df.copy()
    acct = accounts.Account("t", "evaluator") if os.environ.get("CM_EVAL_ROLE") == "evaluator" else accounts.Account("a", "cm_admin")
    ctx = pages.Context(acct, registry.connect(os.environ["CM_TEST_DB"]), accounts.scope_tickets(df, acct), None, Legacy, is_demo=not live)
    pages.page_human_eval(ctx)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "r.db"
    conn = R.connect(path)
    R.build(conn, tmp_path / "nodata", [])
    conn.close()
    monkeypatch.setenv("CM_TEST_DB", str(path))
    return path


@pytest.mark.parametrize("role", ["cm_admin", "evaluator"])
def test_human_evaluation_page_opens_in_demo_mode(db, monkeypatch, role):
    monkeypatch.setenv("CM_EVAL_ROLE", role)
    at = AppTest.from_function(_script, default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    labels = {m.label for m in at.metric}
    assert {"Waiting for a person", "Oldest waiting (days)", "Decided by people", "Jev's first choice kept"} <= labels
    assert any("DEMO DATA" in m.value for m in at.markdown)


def test_human_evaluation_page_falls_back_to_the_plain_queue_for_live_data(db, monkeypatch):
    monkeypatch.setenv("CM_EVAL_LIVE", "1")
    monkeypatch.setenv("CM_EVAL_ROLE", "evaluator")
    at = AppTest.from_function(_script, default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("LIVE QUEUE" in m.value for m in at.markdown)
    assert any("LIVE DATA" in m.value for m in at.markdown)
