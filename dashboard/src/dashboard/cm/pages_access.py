"""The "Desk access" screen of Accounts and Roles (CM office only): who may open each office's complaints.

A complaint is sent to an office (a post), never to a person, because officers are transferred. This screen manages the KEYS to a desk: give a login, hand the desk over to a new person (the old
logins are switched off), reset a forgotten password, switch a login off. No ticket is read or changed here. Logic and storage: cm/desk_access.py (migration 008).
"""

import pandas as pd
import streamlit as st

from dashboard import tickets
from dashboard.cm import accounts, desk_access, ui
from dashboard.safe import md


def _client():
    try:
        from dashboard.db import get_client

        return get_client()
    except Exception:  # noqa: BLE001 -- no database configured on this machine
        return None


def _cm_office_usernames() -> set[str]:
    """Names that belong to the CM office itself (the shared admin login and the accounts file): a desk login may not reuse them."""
    return {"admin", *(a["username"] for a in accounts.load_accounts())}


def _show_secret() -> None:
    """A temporary password is shown ONCE, on the run right after it was made, then forgotten."""
    secret = st.session_state.pop("desk_secret", None)
    if not secret:
        return
    st.success(secret["title"])
    st.code(secret["password"], language=None)
    st.caption(f"Login: **{md(secret['username'])}**. Give this password to the new holder in person or by a call, not in a chat. It is not stored and cannot be shown again. They must choose their own at the first login.")
    if secret.get("switched_off"):
        st.caption("Switched off: " + ", ".join(md(u) for u in secret["switched_off"]))


def desk_access_section(ctx) -> None:
    st.divider()
    st.subheader("Desk access: who can open each office's complaints")
    st.caption(
        "A complaint goes to the office (the post), never to a person, because officers are transferred. Here you decide which logins may open an office's complaints. "
        "Giving, taking away, resetting or handing over a login never changes a ticket."
    )
    if ctx.is_demo or ctx.account.demo_only:
        st.info("This works on the live database. Switch the sidebar Data option to \"Live Samadhan database\".")
        return
    client = _client()
    if client is None:
        st.warning("The database is not reachable from this server.")
        return
    try:
        offices = tickets.list_all_offices(client=client)
    except Exception:  # noqa: BLE001
        st.warning("The list of offices could not be loaded. Try again in a moment.")
        return

    _show_secret()
    actor = ctx.account.username
    departments = sorted({o["department"] for o in offices if o.get("department")})
    department = st.selectbox("Department", departments, key="desk-dept")
    desks = sorted((o for o in offices if o["department"] == department), key=lambda o: (o["level"], o["office_name"]))
    if not desks:
        st.info("This department has no office yet.")
        return
    desk = st.selectbox("Office (desk)", [d["office_name"] for d in desks], key="desk-office", help="Type to search. A desk is a post, for example 'Chief Medical and Health Officer (CMHO), Rajgarh'.")

    try:
        logins = desk_access.list_logins(client, office_name=desk)
    except Exception:  # noqa: BLE001 -- table not created yet
        st.warning("Desk logins are not set up on this database yet. Run `database/migrations/008_dashboard_accounts.sql` in Supabase, then reload.")
        return

    if logins:
        ui.table(
            pd.DataFrame([{
                "login": r["username"], "role": r["role"], "state": "active" if r["active"] else "switched off",
                "temporary password still unchanged": "yes" if r["must_change"] else "no",
                "holder (note)": r.get("label", ""), "made by": r.get("created_by", ""), "last used": str(r.get("last_login_at") or "never")[:16].replace("T", " "),
            } for r in logins]),
            width="stretch", hide_index=True,
        )
    else:
        st.info("Nobody has a login for this desk yet. Its complaints are visible to the CM office and to the department head.")

    give, handover, manage = st.tabs(["Give access", "Hand over this desk", "Reset or switch off a login"])
    taken = _cm_office_usernames()

    with give:
        with st.form("desk-give", clear_on_submit=True):
            username = st.text_input("New login name", placeholder="for example cmho.rajgarh", help="Lower-case letters, digits, dot, dash; start with a letter.", key="give-user")
            role = st.radio("Can see", ["This office only (office officer)", "The whole department (department head)"], horizontal=False, key="give-role")
            note = st.text_input("Who holds it now (note for your own reference)", max_chars=120, key="give-note")
            go = st.form_submit_button("Create login", type="primary")
        if go:
            try:
                temp = desk_access.create_login(
                    client, username=username, role="office_officer" if role.startswith("This") else "dept_head", department=department, office_name=desk,
                    actor=actor, label=note, taken=taken,
                )
            except desk_access.DeskAccessError as exc:
                st.error(str(exc))
            except Exception:  # noqa: BLE001
                st.error("The login could not be created right now. Try again in a moment.")
            else:
                st.session_state["desk_secret"] = {"title": "Login created.", "username": username.strip().lower(), "password": temp}
                st.rerun()

    with handover:
        st.write("Use this when the officer of the desk has changed. **Every active office-officer login of this desk is switched off** and one new login is made. The desk's complaints stay exactly where they are.")
        with st.form("desk-handover", clear_on_submit=True):
            new_username = st.text_input("Login name for the new officer", placeholder="for example cmho.rajgarh2", key="handover-user")
            note = st.text_input("Who holds it now (note)", max_chars=120, key="handover-note")
            confirm = st.checkbox("I understand: the current logins of this desk will stop working", key="handover-confirm")
            go = st.form_submit_button("Hand over the desk", type="primary")
        if go and not confirm:
            st.error("Tick the box to confirm.")
        elif go:
            try:
                temp, switched = desk_access.hand_over(client, office_name=desk, department=department, new_username=new_username, actor=actor, label=note, taken=taken)
            except desk_access.DeskAccessError as exc:
                st.error(str(exc))
            except Exception:  # noqa: BLE001
                st.error("The desk could not be handed over right now. Nothing was changed if you see this; check the list above and try again.")
            else:
                st.session_state["desk_secret"] = {"title": "Desk handed over.", "username": new_username.strip().lower(), "password": temp, "switched_off": switched}
                st.rerun()

    with manage:
        if not logins:
            st.caption("No logins on this desk.")
        else:
            names = [r["username"] for r in logins]
            who = st.selectbox("Login", names, key="desk-manage-user")
            current = next(r for r in logins if r["username"] == who)
            c1, c2 = st.columns(2)
            if c1.button("Reset password", key="desk-reset"):
                try:
                    temp = desk_access.reset_password(client, who, actor)
                except Exception:  # noqa: BLE001
                    st.error("The password could not be reset right now.")
                else:
                    st.session_state["desk_secret"] = {"title": "Password reset.", "username": who, "password": temp}
                    st.rerun()
            label = "Switch off" if current["active"] else "Switch back on"
            if c2.button(label, key="desk-toggle"):
                try:
                    desk_access.set_active(client, who, not current["active"], actor)
                except Exception:  # noqa: BLE001
                    st.error("The change could not be saved right now.")
                else:
                    st.rerun()

    if logins:
        with st.expander("History of this desk's logins"):
            try:
                events = [e for u in names_of(logins) for e in desk_access.list_events(client, username=u, limit=10)]
            except Exception:  # noqa: BLE001
                events = []
            events.sort(key=lambda e: str(e.get("created_at", "")), reverse=True)
            if events:
                ui.table(pd.DataFrame([{"when": str(e["created_at"])[:16].replace("T", " "), "login": e["username"], "what": e["action"], "by": e["actor"], "detail": e.get("detail") or ""} for e in events[:30]]),
                         width="stretch", hide_index=True)
            else:
                st.caption("Nothing recorded yet.")


def names_of(logins: list[dict]) -> list[str]:
    return [r["username"] for r in logins]
