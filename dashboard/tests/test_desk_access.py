"""Desk access: logins that belong to an office (a post), not to a person. Fake database, no network."""

from types import SimpleNamespace

import pandas as pd
import pytest

from dashboard.cm import accounts, desk_access
from dashboard.cm.desk_access import DeskAccessError

DESK = "Chief Medical and Health Officer (CMHO), Rajgarh"
OTHER_DESK = "Chief Medical and Health Officer (CMHO), Sagar"
DEPT = "Public Health and Family Welfare Department"


class FakeDb:
    """Select (with column projection), insert, update, eq filters. A touch of `tickets` raises: access management must never read or change a ticket."""

    def __init__(self):
        self.tables = {"dashboard_accounts": [], "dashboard_account_events": []}
        self._id = 0

    def table(self, name):
        db = self
        if name == "tickets":
            raise AssertionError("desk access must never touch tickets")

        class Q:
            def __init__(self):
                self.op, self.payload, self.cols, self.filters = "select", None, "*", {}

            def select(self, cols="*"):
                self.cols = cols
                return self

            def insert(self, row):
                self.op, self.payload = "insert", row
                return self

            def update(self, row):
                self.op, self.payload = "update", row
                return self

            def eq(self, col, val):
                self.filters[col] = val
                return self

            def execute(self):
                rows = db.tables[name]
                if self.op == "insert":
                    db._id += 1
                    row = {"id": db._id, "created_at": f"2026-10-08T10:{db._id:02d}:00+00:00", "active": True, "must_change": True, "last_login_at": None, **self.payload}
                    rows.append(row)
                    return SimpleNamespace(data=[dict(row)])
                hit = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
                if self.op == "update":
                    for r in hit:
                        r.update(self.payload)
                if self.cols != "*" and self.op == "select":
                    keep = [c.strip() for c in self.cols.split(",")]
                    return SimpleNamespace(data=[{k: r.get(k) for k in keep} for r in hit])
                return SimpleNamespace(data=[dict(r) for r in hit])

        return Q()


@pytest.fixture
def db():
    return FakeDb()


def make(db, username="cmho.rajgarh", **kw):
    args = {"username": username, "role": "office_officer", "department": DEPT, "office_name": DESK, "actor": "admin", "taken": {"admin"}}
    args.update(kw)
    return desk_access.create_login(db, **args)


def test_a_new_login_stores_only_a_hash_and_the_temporary_password_works_once_chosen(db):
    temp = make(db)
    row = db.tables["dashboard_accounts"][0]
    assert temp not in str(row) and "password" not in row  # never stored
    assert accounts.verify_password(temp, row)
    assert row["must_change"] is True and row["active"] is True and row["created_by"] == "admin" and row["office_name"] == DESK
    assert db.tables["dashboard_account_events"][0]["action"] == "created"


def test_list_logins_never_returns_hashes(db):
    make(db)
    for row in desk_access.list_logins(db, office_name=DESK):
        assert "hash" not in row and "salt" not in row and "iterations" not in row


@pytest.mark.parametrize("name", ["ab", "1abc", "Has Space", "bad/char", "x" * 41, ""])
def test_bad_usernames_are_refused(db, name):
    with pytest.raises(DeskAccessError):
        make(db, username=name)


def test_cm_office_names_and_duplicates_are_refused_whatever_the_capitals(db):
    with pytest.raises(DeskAccessError):
        make(db, username="admin")
    with pytest.raises(DeskAccessError):
        make(db, username="cm.office", taken={"CM.Office"})
    make(db, username="cmho.rajgarh")
    with pytest.raises(DeskAccessError):
        make(db, username="CMHO.Rajgarh")
    assert len(db.tables["dashboard_accounts"]) == 1


def test_role_rules(db):
    with pytest.raises(DeskAccessError):
        make(db, role="cm_admin")  # the CM office's own accounts are not handed out here
    with pytest.raises(DeskAccessError):
        make(db, role="office_officer", office_name=None)
    with pytest.raises(DeskAccessError):
        make(db, role="dept_head", department=None)
    make(db, username="head.health", role="dept_head", office_name=DESK)
    assert db.tables["dashboard_accounts"][0]["office_name"] is None  # a department head belongs to the department, not to one desk


def test_reset_gives_a_new_temporary_password_and_the_old_one_stops_working(db):
    old = make(db)
    new = desk_access.reset_password(db, "cmho.rajgarh", "admin")
    row = db.tables["dashboard_accounts"][0]
    assert new != old and accounts.verify_password(new, row) and not accounts.verify_password(old, row) and row["must_change"] is True
    with pytest.raises(DeskAccessError):
        desk_access.reset_password(db, "nobody", "admin")


def test_switching_a_login_off_removes_it_from_the_accounts_that_can_log_in_and_back_on_restores_it(db):
    make(db)
    assert [a["username"] for a in desk_access.active_accounts(db)] == ["cmho.rajgarh"]
    desk_access.set_active(db, "cmho.rajgarh", False, "admin")
    assert desk_access.active_accounts(db) == []
    desk_access.set_active(db, "cmho.rajgarh", True, "admin")
    assert len(desk_access.active_accounts(db)) == 1
    assert [e["action"] for e in db.tables["dashboard_account_events"]] == ["created", "disabled", "enabled"]


def test_handing_over_a_desk_switches_off_its_logins_only_and_makes_one_new_login(db):
    make(db, username="cmho.rajgarh")
    make(db, username="cmho.rajgarh.deputy")
    make(db, username="cmho.sagar", office_name=OTHER_DESK)  # another desk: untouched
    make(db, username="head.health", role="dept_head", office_name=None)  # a department head: untouched
    temp, switched = desk_access.hand_over(db, office_name=DESK, department=DEPT, new_username="cmho.rajgarh.new", actor="admin", taken={"admin"})
    by_name = {r["username"]: r for r in db.tables["dashboard_accounts"]}
    assert sorted(switched) == ["cmho.rajgarh", "cmho.rajgarh.deputy"]
    assert not by_name["cmho.rajgarh"]["active"] and not by_name["cmho.rajgarh.deputy"]["active"]
    assert by_name["cmho.sagar"]["active"] and by_name["head.health"]["active"]
    assert by_name["cmho.rajgarh.new"]["active"] and by_name["cmho.rajgarh.new"]["office_name"] == DESK
    assert accounts.verify_password(temp, by_name["cmho.rajgarh.new"])


def test_a_bad_new_name_changes_nothing_during_a_handover(db):
    make(db, username="cmho.rajgarh")
    with pytest.raises(DeskAccessError):
        desk_access.hand_over(db, office_name=DESK, department=DEPT, new_username="a b", actor="admin", taken={"admin"})
    assert db.tables["dashboard_accounts"][0]["active"] is True  # the old holder keeps access: no desk is ever left without a key by a typo


def test_the_holder_changes_the_temporary_password(db):
    temp = make(db)
    with pytest.raises(DeskAccessError):
        desk_access.change_password(db, "cmho.rajgarh", "wrong password", "a brand new passphrase")
    with pytest.raises(DeskAccessError):
        desk_access.change_password(db, "cmho.rajgarh", temp, "short")
    with pytest.raises(DeskAccessError):
        desk_access.change_password(db, "cmho.rajgarh", temp, temp)
    desk_access.change_password(db, "cmho.rajgarh", temp, "a brand new passphrase")
    row = db.tables["dashboard_accounts"][0]
    assert row["must_change"] is False and accounts.verify_password("a brand new passphrase", row) and not accounts.verify_password(temp, row)


def test_a_switched_off_login_cannot_change_its_password(db):
    temp = make(db)
    desk_access.set_active(db, "cmho.rajgarh", False, "admin")
    with pytest.raises(DeskAccessError):
        desk_access.change_password(db, "cmho.rajgarh", temp, "a brand new passphrase")


def test_a_database_login_signs_in_and_is_marked_so(db):
    temp = make(db)
    found = accounts.authenticate("CMHO.Rajgarh", temp, desk_access.active_accounts(db))
    assert found.role == "office_officer" and found.office_name == DESK and found.extra == {"source": "db", "must_change": True}
    assert accounts.authenticate("cmho.rajgarh", "not the password", desk_access.active_accounts(db)) is None


def test_a_switched_off_login_cannot_sign_in(db):
    temp = make(db)
    desk_access.set_active(db, "cmho.rajgarh", False, "admin")
    assert accounts.authenticate("cmho.rajgarh", temp, desk_access.active_accounts(db)) is None


def test_the_login_sees_only_its_own_desks_tickets(db):
    temp = make(db)
    found = accounts.authenticate("cmho.rajgarh", temp, desk_access.active_accounts(db))
    df = pd.DataFrame({"complaint_id": ["SMD-1", "SMD-2", "SMD-3"], "status": ["new"] * 3, "department": [DEPT, DEPT, "Other"], "office_name": [DESK, OTHER_DESK, DESK]})
    assert list(accounts.scope_tickets(df, found)["complaint_id"]) == ["SMD-1"]


def test_all_accounts_merges_the_file_and_the_database_without_shadowing(db, tmp_path):
    import json

    accounts_file = tmp_path / "a.json"
    accounts_file.write_text(json.dumps({"accounts": [{"username": "evaluator.desk", "role": "evaluator", **accounts.hash_password("x")}]}), encoding="utf-8")
    make(db, username="cmho.rajgarh")
    db.tables["dashboard_accounts"].append({"username": "Evaluator.Desk", "role": "office_officer", "active": True, "salt": "00", "hash": "00", "iterations": 1, "office_name": DESK, "department": DEPT})
    names = [a["username"] for a in accounts.all_accounts(accounts_file, client=db)]
    assert names == ["evaluator.desk", "cmho.rajgarh"]  # the file account wins; the same name in the database is ignored


def test_all_accounts_survives_a_database_that_is_down(tmp_path):
    import json

    accounts_file = tmp_path / "a.json"
    accounts_file.write_text(json.dumps({"accounts": [{"username": "only.file", "role": "evaluator", **accounts.hash_password("x")}]}), encoding="utf-8")

    class Down:
        def table(self, _):
            raise RuntimeError("relation dashboard_accounts does not exist")

    assert [a["username"] for a in accounts.all_accounts(accounts_file, client=Down())] == ["only.file"]


def test_none_of_it_touches_a_ticket(db):
    # FakeDb raises if table('tickets') is ever opened; run every operation
    make(db)
    desk_access.reset_password(db, "cmho.rajgarh", "admin")
    desk_access.set_active(db, "cmho.rajgarh", False, "admin")
    temp, _ = desk_access.hand_over(db, office_name=DESK, department=DEPT, new_username="cmho.rajgarh.new", actor="admin", taken={"admin"})
    desk_access.change_password(db, "cmho.rajgarh.new", temp, "a brand new passphrase")
    desk_access.list_logins(db)
    desk_access.list_events(db)
    assert len(db.tables["dashboard_accounts"]) == 2


def test_a_missing_events_table_never_blocks_the_action(db):
    class NoEvents(FakeDb):
        def table(self, name):
            if name == "dashboard_account_events":
                raise RuntimeError("no such table")
            return super().table(name)

    assert make(NoEvents())  # returns the temporary password, the login exists, only its history line was lost
