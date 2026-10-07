"""A citizen's request to be forgotten: what is removed, what stays, and that nobody else is touched."""

from types import SimpleNamespace

import pytest

from app import data_rights


class FakeDb:
    """Just enough of the Supabase client: select / update / delete with eq filters, and storage.remove."""

    def __init__(self):
        self.tables = {
            "users": [{"id": "u1", "phone": "+919876543210"}, {"id": "u2", "phone": "+919000000001"}],
            "tickets": [
                {"complaint_id": "SMD-0001", "session_id": "s1", "audio_path": "s1/a.webm", "user_id": "u1"},
                {"complaint_id": "SMD-0002", "session_id": "s2", "audio_path": None, "user_id": "u1"},
                {"complaint_id": "SMD-0003", "session_id": "s3", "audio_path": "s3/c.webm", "user_id": "u2"},
            ],
            "messages": [
                {"session_id": "s1", "audio_path": "s1/a.webm"},
                {"session_id": "s1", "audio_path": "s1/b.webm"},
                {"session_id": "s2", "audio_path": None},
                {"session_id": "s3", "audio_path": "s3/c.webm"},
            ],
            "auth_sessions": [{"id": "a1", "user_id": "u1"}, {"id": "a2", "user_id": "u2"}],
            "auth_challenges": [{"id": "c1", "phone": "+919876543210"}, {"id": "c2", "phone": "+919000000001"}],
        }
        self.removed: list[str] = []
        self.storage = SimpleNamespace(from_=lambda bucket: SimpleNamespace(remove=lambda paths: self.removed.extend(paths)))

    def table(self, name):
        db = self

        class Q:
            def __init__(self):
                self.op, self.payload, self.filters = "select", None, {}

            def select(self, *_):
                return self

            def update(self, row):
                self.op, self.payload = "update", row
                return self

            def delete(self):
                self.op = "delete"
                return self

            def eq(self, col, val):
                self.filters[col] = val
                return self

            def execute(self):
                rows = db.tables[name]
                hit = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
                if self.op == "update":
                    for r in hit:
                        r.update(self.payload)
                elif self.op == "delete":
                    db.tables[name] = [r for r in rows if r not in hit]
                return SimpleNamespace(data=[dict(r) for r in hit])

        return Q()


def test_plan_lists_the_citizens_complaints_recordings_and_logins():
    found = data_rights.plan(FakeDb(), "98765 43210")
    assert found.user_id == "u1"
    assert found.complaint_ids == ["SMD-0001", "SMD-0002"]
    assert sorted(found.audio_paths) == ["s1/a.webm", "s1/b.webm"]  # the ticket's file and the other message's file, once each
    assert found.login_sessions == 1


def test_plan_changes_nothing():
    db = FakeDb()
    before = {k: [dict(r) for r in v] for k, v in db.tables.items()}
    data_rights.plan(db, "9876543210")
    assert db.tables == before and db.removed == []


def test_unknown_number_is_a_clean_none():
    assert data_rights.plan(FakeDb(), "9111111111") is None
    assert data_rights.erase(FakeDb(), "9111111111") is None


def test_erase_removes_the_number_logins_and_recordings_but_keeps_the_complaints():
    db = FakeDb()
    data_rights.erase(db, "9876543210")

    assert [u["id"] for u in db.tables["users"]] == ["u2"]
    assert all(r["user_id"] != "u1" for r in db.tables["auth_sessions"])
    assert [c["phone"] for c in db.tables["auth_challenges"]] == ["+919000000001"]
    assert sorted(db.removed) == ["s1/a.webm", "s1/b.webm"]
    kept = {t["complaint_id"]: t for t in db.tables["tickets"]}
    assert set(kept) == {"SMD-0001", "SMD-0002", "SMD-0003"}  # the government's record stays
    assert kept["SMD-0001"]["user_id"] is None and kept["SMD-0001"]["audio_path"] is None
    assert kept["SMD-0002"]["user_id"] is None


def test_erase_never_touches_another_citizen():
    db = FakeDb()
    data_rights.erase(db, "9876543210")
    other = next(t for t in db.tables["tickets"] if t["complaint_id"] == "SMD-0003")
    assert other["user_id"] == "u2" and other["audio_path"] == "s3/c.webm"
    assert "s3/c.webm" not in db.removed
    assert {m["audio_path"] for m in db.tables["messages"] if m["session_id"] == "s3"} == {"s3/c.webm"}


def test_a_bad_number_is_refused_before_any_database_call():
    from app.auth import AuthError

    with pytest.raises(AuthError):
        data_rights.plan(FakeDb(), "12345")
