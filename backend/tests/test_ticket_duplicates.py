"""Audit M1: a double tap or a retry must not file the complaint twice, and two genuinely different complaints must still become two tickets."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app import ticketing
from app.ticketing import create_ticket
from tests.test_ticketing import DISTRICT, SPEC, FakeClient, ward


def _seen(minutes_ago: float, **over) -> dict:
    row = {
        "id": 77,
        "complaint_id": "SMD-0077",
        "session_id": over.pop("session_id"),
        "service_id": "water_supply",
        "original_text": "no water since 3 days",
        "status": "new",
        "office_id": 99,
        "created_at": (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat(),
    }
    row.update(over)
    return row


def _file(client, session_id, text="no water since 3 days", **kw):
    return create_ticket(
        session_id=session_id,
        spec=SPEC,
        validated_fields={"issue_type": "no_supply", "location": "Misrod"},
        lat=None,
        lng=None,
        original_text=text,
        audio_path=None,
        client=client,
        **kw,
    )


@pytest.fixture
def client():
    return FakeClient([ward(1, "Misrod", aliases=["Misrod"]), DISTRICT])


def test_the_same_complaint_a_moment_later_returns_the_same_ticket_and_inserts_nothing(client):
    sid = uuid.uuid4()
    client.tables["tickets"].append(_seen(0.5, session_id=str(sid)))

    ticket = _file(client, sid)

    assert ticket.complaint_id == "SMD-0077"
    assert len(client.tables["tickets"]) == 1  # nothing new was inserted
    assert ticket.office.name == "BMC Head Office"


def test_a_different_complaint_in_the_same_chat_is_a_new_ticket(client):
    sid = uuid.uuid4()
    client.tables["tickets"].append(_seen(0.5, session_id=str(sid)))

    ticket = _file(client, sid, text="street light broken")

    assert ticket.complaint_id != "SMD-0077"
    assert len(client.tables["tickets"]) == 2


def test_the_same_text_in_another_chat_is_a_new_ticket(client):
    client.tables["tickets"].append(_seen(0.5, session_id=str(uuid.uuid4())))

    ticket = _file(client, uuid.uuid4())

    assert ticket.complaint_id != "SMD-0077"


def test_an_old_ticket_does_not_swallow_a_genuine_second_complaint(client):
    sid = uuid.uuid4()
    client.tables["tickets"].append(_seen(10, session_id=str(sid)))  # ten minutes ago: outside the window

    ticket = _file(client, sid)

    assert ticket.complaint_id != "SMD-0077"
    assert len(client.tables["tickets"]) == 2


def test_a_database_error_in_the_duplicate_check_still_files_the_complaint(client, monkeypatch):
    monkeypatch.setattr(ticketing, "_age_seconds", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    sid = uuid.uuid4()
    client.tables["tickets"].append(_seen(0.5, session_id=str(sid)))

    ticket = _file(client, sid)  # must not raise

    assert ticket.complaint_id != "SMD-0077"


def test_a_missing_created_at_or_office_never_blocks_filing(client):
    sid = uuid.uuid4()
    broken = _seen(0.5, session_id=str(sid))
    del broken["created_at"]
    client.tables["tickets"].append(broken)

    assert _file(client, sid).complaint_id != "SMD-0077"


def test_age_seconds_reads_z_and_naive_times_and_rejects_garbage():
    assert 0 <= ticketing._age_seconds(datetime.now(UTC).isoformat().replace("+00:00", "Z")) < 5
    assert 0 <= ticketing._age_seconds(datetime.now(UTC).replace(tzinfo=None).isoformat()) < 5
    assert ticketing._age_seconds("not a date") is None
    assert isinstance(SimpleNamespace(), SimpleNamespace)


# --- a department with no offices yet must not lose the complaint --------------------------------------------


def test_a_department_without_offices_sends_the_complaint_to_human_evaluation_for_review():
    human_desk = {**DISTRICT, "id": 500, "office_name": "Human Evaluation Desk (DEMO)", "department": "Human Evaluation", "active": True}
    client = FakeClient([human_desk])  # nothing at all for the spec's own department

    ticket = _file(client, uuid.uuid4())

    assert ticket.office.name == "Human Evaluation Desk (DEMO)"
    assert ticket.status == "needs_review"
    assert client.tables["tickets"][-1]["office_id"] == 500
    assert client.tables["tickets"][-1]["department"] == SPEC.department  # the ticket still says which department it was meant for


def test_if_even_the_human_evaluation_desk_is_missing_the_error_is_raised_not_hidden():
    from app.jurisdiction import JurisdictionError

    with pytest.raises(JurisdictionError):
        _file(FakeClient([]), uuid.uuid4())
