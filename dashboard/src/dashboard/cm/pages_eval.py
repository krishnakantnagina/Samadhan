"""Human Evaluation: complaints the AI could not place with confidence.

Flow this page belongs to (decided with the Lead): Jev picks the department; if the location is unclear the bot asks district / tehsil / nearest
known place; if Jev is torn between departments it asks ONE question about the problem Jev suggests most; if it is still not confirmed the
complaint lands here for a person. Each decision is recorded, so the AI's rules can be tightened from what people actually decide.

Demo mode shows the full experience on invented tickets (edits stay in the browser session). Live mode shows the `needs_review` queue; live tickets do
not store Jev's candidates or the follow-up questions yet (the intake loop is not built), so only the basic columns exist there.
"""

import pandas as pd
import streamlit as st

from dashboard.cm import theme, ui
from dashboard.cm.departments import ALL_DEPARTMENTS

REASON_LABEL = {
    "department_unconfirmed": "Department not confirmed after the follow-up question",
    "location_unclear": "Location still unclear after asking district / tehsil",
    "vague_description": "Problem description too vague",
}


def _now() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")


def _age_days(created: pd.Series) -> pd.Series:
    return ((pd.Timestamp.now(tz="UTC") - pd.to_datetime(created, utc=True, format="ISO8601")).dt.total_seconds() / 86400).round(1)


def insights(df: pd.DataFrame) -> dict:
    """Numbers for the top of the page. Pure pandas so it can be tested: queue size, oldest wait, how often a person kept Jev's first choice, confused pairs."""
    queue = df[df["status"] == "needs_review"]
    done = df[df["evaluated_by"].fillna("") != ""] if "evaluated_by" in df else df.iloc[0:0]
    agree = float((done["jev_top"] == done["department"]).mean() * 100) if len(done) else None
    pairs = pd.concat([queue[["jev_top", "jev_second"]].rename(columns={"jev_top": "a", "jev_second": "b"}),
                       done[done["jev_top"] != done["department"]][["jev_top", "department"]].rename(columns={"jev_top": "a", "department": "b"})]) if "jev_top" in df else pd.DataFrame(columns=["a", "b"])
    confused = (pairs.assign(pair=pairs.apply(lambda r: " vs ".join(sorted([str(r["a"]), str(r["b"])])), axis=1)).groupby("pair").size().sort_values(ascending=False).head(8)
                .rename("times").reset_index()) if not pairs.empty else pd.DataFrame(columns=["pair", "times"])
    return {"waiting": len(queue), "oldest_days": float(_age_days(queue["created_at"]).max()) if len(queue) else 0.0, "evaluated": len(done),
            "agree_pct": None if agree is None else round(agree, 1), "avg_questions": round(float(queue["questions_asked"].mean()), 1) if len(queue) else 0.0, "confused": confused}


def _decide(store: pd.DataFrame, complaint_id: str, department: str | None, evaluator: str, note: str) -> None:
    """Apply one human decision to the session copy of the demo tickets (nothing is written anywhere else)."""
    idx = store.index[store["complaint_id"] == complaint_id][0]
    for col in ("evaluated_by", "evaluated_dept", "eval_note"):
        if col not in store:
            store[col] = ""
    if department is None:  # not a government grievance: close it
        store.loc[idx, ["status", "evaluated_by", "evaluated_dept", "eval_note", "updated_at"]] = ["resolved", evaluator, "(not a grievance)", note, _now()]
        return
    district = store.loc[idx, "district"]
    store.loc[idx, ["status", "department", "office_name", "evaluated_by", "evaluated_dept", "eval_note", "updated_at"]] = [
        "new", department, f"{department} office, {district} (demo)", evaluator, department, note, _now()]


def page_human_eval(ctx) -> None:
    from dashboard.cm.pages import _badge, _need_tickets

    st.title("Human Evaluation")
    _badge(ctx)
    st.caption("Complaints the AI could not place with confidence. Jev's best guess and one follow-up question did not settle it, so a person decides. "
               "Every decision is recorded, so the AI's rules can be tightened from what people actually choose.")
    if not _need_tickets(ctx):
        return
    df = ctx.df
    if not (ctx.is_demo and "eval_reason" in df):
        queue = df[df["status"] == "needs_review"]
        st.info("Live tickets do not yet store Jev's candidate departments or the follow-up questions (the intake loop is not built), so this shows the plain needs_review queue.")
        if queue.empty:
            st.success("Nothing is waiting.")
        else:
            ctx.legacy._ticket_table(queue, key="cm-human-eval", can_reassign=ctx.account.can_reassign, allowed_departments=ctx.account.reassign_departments())
        return

    info = insights(df)
    k = st.columns(4)
    k[0].metric("Waiting for a person", info["waiting"])
    k[1].metric("Oldest waiting (days)", info["oldest_days"])
    k[2].metric("Decided by people", info["evaluated"])
    k[3].metric("Jev's first choice kept", "-" if info["agree_pct"] is None else f"{info['agree_pct']}%", help="Of tickets a person decided: how often the final department was Jev's first suggestion")
    t_queue, t_insight = st.tabs(["Queue", "What this teaches the AI"])
    with t_queue:
        queue = df[df["status"] == "needs_review"].copy()
        if queue.empty:
            st.success("Nothing is waiting for evaluation.")
            return
        reason = st.selectbox("Why it is here", ["all", *REASON_LABEL], format_func=lambda r: "All reasons" if r == "all" else REASON_LABEL[r], key="he-reasons")
        queue = queue if reason == "all" else queue[queue["eval_reason"] == reason]
        queue["waiting_days"] = _age_days(queue["created_at"])
        queue["jev_first"] = queue["jev_top"] + " (" + (queue["jev_top_p"] * 100).round(0).astype(int).astype(str) + "%)"
        queue["jev_second_choice"] = queue["jev_second"] + " (" + (queue["jev_second_p"] * 100).round(0).astype(int).astype(str) + "%)"
        queue = queue.sort_values("waiting_days", ascending=False)
        show = queue[["complaint_id", "eval_reason", "jev_first", "jev_second_choice", "questions_asked", "district", "location_quality", "waiting_days"]]
        st.caption(f"{len(queue)} waiting, longest first. Select one to decide.")
        ev = ui.table(show, width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key=f"he-table-{len(queue)}")
        rows = ev.selection["rows"]
        if not rows:
            return
        row = queue.iloc[rows[0]]
        st.divider()
        st.subheader(row["complaint_id"])
        st.markdown(f'<div class="cm-card"><b>Citizen said</b><br><span style="font-size:1.15rem">“{row["citizen_message"]}”</span><br>'
                    f'<small>{row["summary_en"]} · {row["district"]} district ({row["division"]} division) · location precision: {row["location_quality"]} · '
                    f'duration: {"%d days" % row["duration_days"] if pd.notna(row["duration_days"]) else "not given"}</small></div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.write("**Why a person is needed**")
        c1.write(REASON_LABEL.get(row["eval_reason"], row["eval_reason"]))
        c1.caption(f"Questions asked before giving up: {row['questions_asked']}")
        c2.write("**What Jev suggested**")
        c2.dataframe(pd.DataFrame([{"department": row["jev_top"], "probability": row["jev_top_p"]}, {"department": row["jev_second"], "probability": row["jev_second_p"]}]),
                     width="stretch", hide_index=True)
        names = sorted({d[1] for d in ALL_DEPARTMENTS} | set(df["department"].unique()) - {"Human Evaluation"})
        choice = st.radio("Decision", [f"Jev's first choice: {row['jev_top']}", f"Jev's second choice: {row['jev_second']}", "Another department", "Not a government grievance (close it)"],
                          key=f"he-choice-{row['complaint_id']}")
        other = st.selectbox("Department", names, key=f"he-other-{row['complaint_id']}") if choice == "Another department" else None
        note = st.text_input("Note (why)", key=f"he-note-{row['complaint_id']}")
        if st.button("Confirm decision", key=f"he-go-{row['complaint_id']}"):
            target = row["jev_top"] if choice.startswith("Jev's first") else row["jev_second"] if choice.startswith("Jev's second") else other
            _decide(st.session_state["demo_df"], row["complaint_id"], None if choice.startswith("Not") else target, ctx.account.username, note)
            st.rerun()
        st.caption("Demo data: decisions stay in this browser session only. In production each one would be stored with who decided and why.")
    with t_insight:
        st.subheader("Why complaints reach a person")
        q = df[df["status"] == "needs_review"]
        if not q.empty:
            st.bar_chart(q["eval_reason"].map(REASON_LABEL).value_counts(), color=theme.BLUE)
        st.subheader("Department pairs Jev confuses most")
        st.caption("Pairs from the waiting queue plus the cases where a person overruled Jev. These are the pairs worth a written tie-breaker question "
                   "(for example School Education vs Higher Education: 'school or college?').")
        if info["confused"].empty:
            st.success("No confusion recorded yet.")
        else:
            ui.table(info["confused"], width="stretch", hide_index=True)
