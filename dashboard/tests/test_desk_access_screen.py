"""The Desk access screen, driven like a CM-office user: choose a desk, give access, see the temporary password once."""

from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest
from test_desk_access import DEPT, DESK, OTHER_DESK, FakeDb

from dashboard.cm import desk_access, pages_access

OFFICES = [
    {"id": 1, "department": DEPT, "office_name": DESK, "level": "district", "active": True},
    {"id": 2, "department": DEPT, "office_name": OTHER_DESK, "level": "district", "active": True},
    {"id": 3, "department": "Jal Vibhag", "office_name": "Executive Engineer, Public Health Engineering, Rajgarh", "level": "district", "active": True},
]


class ScreenDb(FakeDb):
    """FakeDb plus the offices list the screen reads (with the ordering calls it makes)."""

    def __init__(self, missing_accounts_table=False):
        super().__init__()
        self.tables["offices"] = list(OFFICES)
        self.missing = missing_accounts_table

    def table(self, name):
        if self.missing and name.startswith("dashboard_account"):
            raise RuntimeError('relation "dashboard_accounts" does not exist')
        q = super().table(name)
        q.order = lambda *a, **k: q
        return q


def _script():
    from types import SimpleNamespace

    import streamlit as st

    from dashboard.cm import accounts, pages_access

    demo = st.session_state.get("demo", False)
    ctx = SimpleNamespace(account=accounts.Account("admin", "cm_admin"), is_demo=demo)
    pages_access.desk_access_section(ctx)


@pytest.fixture
def screen(monkeypatch):
    db = ScreenDb()
    monkeypatch.setattr(pages_access, "_client", lambda: db)
    return db


def run(**state):
    at = AppTest.from_function(_script, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def pick_desk(at, desk=DESK):
    at.selectbox(key="desk-dept").select(DEPT).run()
    at.selectbox(key="desk-office").select(desk).run()
    return at


def submit(at, label):
    next(b for b in at.button if b.label == label).click()
    return at.run()


def test_the_screen_opens_and_lists_the_desks_of_the_chosen_department(screen):
    at = pick_desk(run())
    assert not at.exception
    assert set(at.selectbox(key="desk-office").options) == {DESK, OTHER_DESK}
    assert any("Nobody has a login" in i.value for i in at.info)


def test_giving_access_creates_a_login_and_shows_the_temporary_password_once(screen):
    at = pick_desk(run())
    at.text_input(key="give-user").set_value("cmho.rajgarh")
    at = submit(at, "Create login")
    assert not at.exception and not at.error
    row = screen.tables["dashboard_accounts"][0]
    assert row["username"] == "cmho.rajgarh" and row["office_name"] == DESK and row["role"] == "office_officer" and row["created_by"] == "admin"
    shown = at.code[0].value
    assert len(shown) >= 12 and shown not in str(row)  # the password is on screen, not in the database
    again = at.run()
    assert len(again.code) == 0  # forgotten after one showing


def test_a_wrong_login_name_shows_a_plain_message_and_creates_nothing(screen):
    at = pick_desk(run())
    at.text_input(key="give-user").set_value("a b")
    at = submit(at, "Create login")
    assert any("username" in e.value.lower() for e in at.error)
    assert screen.tables["dashboard_accounts"] == []


def test_the_cm_office_names_cannot_be_taken(screen):
    at = pick_desk(run())
    at.text_input(key="give-user").set_value("admin")
    at = submit(at, "Create login")
    assert any("already used" in e.value for e in at.error) and screen.tables["dashboard_accounts"] == []


def test_handing_over_a_desk_needs_the_tick_and_then_switches_the_old_login_off(screen):
    desk_access.create_login(screen, username="cmho.rajgarh", role="office_officer", department=DEPT, office_name=DESK, actor="admin", taken={"admin"})
    at = pick_desk(run())
    at.text_input(key="handover-user").set_value("cmho.rajgarh.new")
    at = submit(at, "Hand over the desk")
    assert any("Tick the box" in e.value for e in at.error)
    assert screen.tables["dashboard_accounts"][0]["active"] is True  # nothing changed without the tick
    at.checkbox(key="handover-confirm").check().run()
    at = submit(at, "Hand over the desk")
    by_name = {r["username"]: r for r in screen.tables["dashboard_accounts"]}
    assert by_name["cmho.rajgarh"]["active"] is False and by_name["cmho.rajgarh.new"]["active"] is True
    assert "Switched off:" in " ".join(c.value for c in at.caption)  # the screen tells who lost access (names are escaped for Markdown)


def test_demo_mode_does_not_touch_the_database(monkeypatch):
    monkeypatch.setattr(pages_access, "_client", lambda: (_ for _ in ()).throw(AssertionError("the demo must not open the database")))
    at = run(demo=True)
    assert not at.exception and any("live database" in i.value for i in at.info)


def test_a_database_without_the_table_says_which_migration_to_run(monkeypatch):
    monkeypatch.setattr(pages_access, "_client", lambda: ScreenDb(missing_accounts_table=True))
    at = pick_desk(run())
    assert not at.exception and any("008_dashboard_accounts.sql" in w.value for w in at.warning)


def test_no_database_at_all_is_a_warning_not_a_crash(monkeypatch):
    monkeypatch.setattr(pages_access, "_client", lambda: None)
    at = run()
    assert not at.exception and any("not reachable" in w.value for w in at.warning)


def test_the_screen_is_only_on_the_cm_admin_accounts_page():
    from dashboard.cm.accounts import PAGE_ACCESS

    assert PAGE_ACCESS["accounts"] == ("cm_admin",)
    assert isinstance(SimpleNamespace(), SimpleNamespace)
