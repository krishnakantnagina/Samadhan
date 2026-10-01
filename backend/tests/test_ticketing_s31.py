"""S31: structured location columns, the registered citizen on the ticket, and the safe fallback when the database lacks the new columns."""

import uuid

import pytest

from app.ticketing import create_ticket
from test_ticketing import DISTRICT, SPEC, FakeClient, _Query

NOTES = {"_intake": {"reason": "confident", "location_details": {"district": "Shajapur", "district_hi": "शाजापुर", "tehsil": "कालापीपल"}}}
FIELDS = {"issue_type": "no_supply", "location": "किलोजा"}


def make(client, fields=None, lat=None, lng=None, **kw):
    return create_ticket(session_id=uuid.uuid4(), spec=SPEC, validated_fields=fields or {**FIELDS, **NOTES}, lat=lat, lng=lng, original_text="x", audio_path=None, client=client, **kw)


def stored(client):
    return client.tables["tickets"][-1]


def test_structured_location_is_written_as_columns():
    client = FakeClient([DISTRICT])
    make(client)
    row = stored(client)
    assert (row["district"], row["tehsil"], row["nearest_place"], row["location_precision"]) == ("Shajapur", "कालापीपल", None, "village")


def test_precision_is_exact_with_gps_district_without_a_place_and_unknown_when_nothing_is_known():
    c1 = FakeClient([DISTRICT])
    make(c1, lat=23.2, lng=77.4)
    assert stored(c1)["location_precision"] == "exact"
    c2 = FakeClient([DISTRICT])
    make(c2, fields={"issue_type": "no_supply", **NOTES})  # a district but no named place
    assert stored(c2)["location_precision"] == "district"
    c3 = FakeClient([DISTRICT])
    make(c3, fields={**FIELDS, "_intake": {"location_details": {"unknown": True}}})
    assert (stored(c3)["district"], stored(c3)["location_precision"]) == (None, "unknown")


def test_tickets_without_intake_notes_are_written_exactly_as_before():
    client = FakeClient([DISTRICT])
    make(client, fields=dict(FIELDS))
    row = stored(client)
    assert not {"district", "tehsil", "nearest_place", "location_precision", "user_id"} & set(row)


def test_the_registered_citizen_is_linked_to_the_ticket():
    client = FakeClient([DISTRICT])
    uid = uuid.uuid4()
    make(client, user_id=uid)
    assert stored(client)["user_id"] == str(uid)


class MissingColumnClient(FakeClient):
    """Behaves like a database where migration 002 has not been applied: an insert that names a new column fails."""

    def __init__(self, offices, error="Could not find the 'district' column of 'tickets' in the schema cache"):
        super().__init__(offices)
        self.error, self.attempts = error, []

    def table(self, name):
        query = _Query(self, name)
        if name != "tickets":
            return query
        real_insert = query.insert

        def insert(row):
            self.attempts.append(dict(row))
            if "district" in row:
                raise RuntimeError(self.error)
            return real_insert(row)

        query.insert = insert
        return query


def test_a_missing_column_never_loses_the_complaint():
    client = MissingColumnClient([DISTRICT])
    ticket = make(client, user_id=uuid.uuid4())
    assert ticket.complaint_id.startswith("SMD-")
    assert len(client.attempts) == 2 and "district" in client.attempts[0] and not ({"district", "user_id", "location_precision"} & set(client.attempts[1]))
    assert stored(client)["fields"]["_intake"]["location_details"]["district"] == "Shajapur"  # the notes still travel inside fields


def test_other_database_errors_are_not_swallowed():
    client = MissingColumnClient([DISTRICT], error="connection refused")
    with pytest.raises(RuntimeError, match="connection refused"):
        make(client)
    assert len(client.attempts) == 1
