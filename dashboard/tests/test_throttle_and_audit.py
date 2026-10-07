"""Login lockout (audit H6) and the officer audit trail (migration 006)."""

from types import SimpleNamespace

import pytest

from dashboard.throttle import LoginThrottle, locked_message
from dashboard.tickets import list_events, reassign_ticket, record_event, update_status


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(**kw):
    clock = Clock()
    return LoginThrottle(clock=clock, **kw), clock


def test_five_wrong_tries_lock_that_username_for_ten_minutes():
    throttle, clock = make()
    for _ in range(4):
        throttle.record_failure("Admin")
        assert throttle.seconds_locked("admin") == 0
    throttle.record_failure("admin")  # the fifth, whatever the capitalisation
    assert 590 <= throttle.seconds_locked("ADMIN") <= 601
    clock.now += 601
    assert throttle.seconds_locked("admin") == 0


def test_other_usernames_are_not_locked_by_one_users_failures():
    throttle, _ = make()
    for _ in range(5):
        throttle.record_failure("admin")
    assert throttle.seconds_locked("evaluator1") == 0


def test_failures_outside_the_window_do_not_add_up():
    throttle, clock = make()
    for _ in range(4):
        throttle.record_failure("admin")
        clock.now += 200  # 800 s later the first ones have expired
    throttle.record_failure("admin")
    assert throttle.seconds_locked("admin") == 0


def test_success_clears_the_failures():
    throttle, _ = make()
    for _ in range(4):
        throttle.record_failure("admin")
    throttle.record_success("admin")
    for _ in range(4):
        throttle.record_failure("admin")
    assert throttle.seconds_locked("admin") == 0


def test_spraying_many_usernames_trips_the_global_lock():
    throttle, _ = make(global_max_failures=10)
    for i in range(10):
        throttle.record_failure(f"user{i}")  # each name only once: no per-username lock
    assert throttle.seconds_locked("someone-else") > 0


def test_message_rounds_up_to_minutes():
    assert "1 minute" in locked_message(5)
    assert "10 minute" in locked_message(600)


# --- audit trail -----------------------------------------------------------------------------------------


class FakeClient:
    def __init__(self, fail_events=False):
        self.rows: dict[str, list[dict]] = {"ticket_events": [], "routing_corrections": [], "tickets": [], "offices": [{"department": "Dept B"}]}
        self.fail_events = fail_events

    def table(self, name):
        client = self

        class Q:
            def __init__(self):
                self.op = None
                self.payload = None

            def insert(self, row):
                if name == "ticket_events" and client.fail_events:
                    raise RuntimeError("relation ticket_events does not exist")
                self.op, self.payload = "insert", row
                return self

            def update(self, row):
                self.op, self.payload = "update", row
                return self

            def select(self, *_):
                self.op = "select"
                return self

            def eq(self, *_):
                return self

            def order(self, *_a, **_k):
                return self

            def limit(self, *_):
                return self

            def execute(self):
                if self.op == "insert":
                    client.rows[name].append(self.payload)
                if self.op == "select" and name == "ticket_events" and client.fail_events:
                    raise RuntimeError("relation ticket_events does not exist")
                return SimpleNamespace(data=list(client.rows.get(name, [])))

        return Q()


def test_status_change_is_recorded_with_who_and_from_to():
    client = FakeClient()
    update_status("SMD-0007", "resolved", actor="evaluator1", previous="new", client=client)
    assert client.rows["ticket_events"] == [{"complaint_id": "SMD-0007", "actor": "evaluator1", "action": "status_changed", "detail": "new -> resolved"}]


def test_no_actor_means_no_audit_row_and_the_old_call_still_works():
    client = FakeClient()
    update_status("SMD-0007", "resolved", client=client)
    assert client.rows["ticket_events"] == []


def test_reassign_is_recorded_with_the_reason():
    client = FakeClient()
    reassign_ticket(ticket_id=5, from_office_id=1, to_office_id=2, reason="wrong dept", actor="admin", complaint_id="SMD-0005", client=client)
    event = client.rows["ticket_events"][0]
    assert (event["actor"], event["action"], event["detail"]) == ("admin", "reassigned", "office 1 -> 2: wrong dept")


def test_a_missing_audit_table_never_blocks_the_officers_action():
    client = FakeClient(fail_events=True)
    update_status("SMD-0007", "resolved", actor="admin", previous="new", client=client)  # must not raise
    record_event("SMD-0007", "admin", "viewed_phone", client=client)  # must not raise
    assert list_events("SMD-0007", client=client) == []


def test_list_events_returns_rows():
    client = FakeClient()
    record_event("SMD-0001", "admin", "viewed_phone", client=client)
    assert [e["action"] for e in list_events("SMD-0001", client=client)] == ["viewed_phone"]


@pytest.mark.parametrize("name", ["officer", "admin"])
def test_the_shared_instance_exists(name):
    from dashboard.throttle import LOGIN_THROTTLE

    assert LOGIN_THROTTLE.seconds_locked(name) == 0
