import pandas as pd

from dashboard.cm import accounts
from dashboard.cm.make_demo_accounts import build

TICKETS = pd.DataFrame(
    {
        "complaint_id": ["SMD-1", "SMD-2", "SMD-3", "SMD-4", "SMD-5"],
        "department": ["Jal Vibhag", "Jal Vibhag", "Bijli Vibhag", "Human Evaluation", "Lok Nirman Vibhag"],
        "office_name": ["Ward A", "Ward B", "Ward A", "Desk", "Ward A"],
        "status": ["new", "needs_review", "new", "needs_review", "needs_review"],
    }
)


def test_password_round_trip_and_wrong_password():
    record = accounts.hash_password("s3cret")
    assert accounts.verify_password("s3cret", record)
    assert not accounts.verify_password("s3creT", record)
    assert accounts.hash_password("s3cret")["salt"] != record["salt"]  # per-account salt


def test_authenticate_unknown_user_wrong_password_and_legacy():
    recs = [{"username": "jal.head", "role": "dept_head", "department": "Jal Vibhag", **accounts.hash_password("pw")}]
    assert accounts.authenticate("JAL.head", "pw", recs).department == "Jal Vibhag"
    assert accounts.authenticate("jal.head", "nope", recs) is None
    assert accounts.authenticate("ghost", "pw", recs) is None
    assert accounts.authenticate("admin", "shared", recs, legacy_password="shared").role == "cm_admin"
    assert accounts.authenticate("admin", "wrong", recs, legacy_password="shared") is None
    assert accounts.authenticate("admin", "shared", recs) is None  # no legacy password configured


def test_unknown_role_in_file_is_rejected():
    recs = [{"username": "x", "role": "god", **accounts.hash_password("pw")}]
    assert accounts.authenticate("x", "pw", recs) is None


def test_dept_head_never_sees_another_department():
    head = accounts.Account("jal.head", "dept_head", department="Jal Vibhag")
    assert set(accounts.scope_tickets(TICKETS, head)["complaint_id"]) == {"SMD-1", "SMD-2"}


def test_office_officer_sees_only_their_office_and_cannot_reassign():
    officer = accounts.Account("o", "office_officer", department="Jal Vibhag", office_name="Ward A")
    assert list(accounts.scope_tickets(TICKETS, officer)["complaint_id"]) == ["SMD-1"]
    assert not officer.can_reassign


def test_triage_sees_general_and_every_review_ticket():
    triage = accounts.Account("t", "evaluator")
    assert set(accounts.scope_tickets(TICKETS, triage)["complaint_id"]) == {"SMD-2", "SMD-4", "SMD-5"}
    assert triage.reassign_departments() is None


def test_admin_sees_everything_and_head_can_only_reassign_inside_department():
    assert len(accounts.scope_tickets(TICKETS, accounts.Account("a", "cm_admin"))) == 5
    assert accounts.Account("h", "dept_head", department="Jal Vibhag").reassign_departments() == {"Jal Vibhag"}


def test_scoped_role_without_scope_fails_closed():
    assert accounts.scope_tickets(TICKETS, accounts.Account("h", "dept_head")).empty
    assert accounts.scope_tickets(TICKETS, accounts.Account("o", "office_officer", department="Jal Vibhag")).empty


def test_page_access_by_role():
    head = accounts.Account("h", "dept_head", department="Jal Vibhag")
    assert head.can_open("my_department") and head.can_open("tickets")
    assert not head.can_open("departments") and not head.can_open("accounts") and not head.can_open("data")
    assert accounts.Account("a", "cm_admin").can_open("accounts")


def test_demo_account_builder_covers_every_role_and_hashes_passwords():
    records, plain = build()
    assert {r["role"] for r in records} == set(accounts.ROLES)
    assert len(records) == len(plain) == 10  # admin + 4 heads + 4 ward officers + triage
    assert all("password" not in r and len(r["hash"]) == 64 for r in records)
    for (user, pw, _role, _d), rec in zip(plain, records, strict=True):
        assert user == rec["username"] and accounts.verify_password(pw, rec)
