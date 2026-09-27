"""S13/S14 -- dashboard/tickets.py against a minimal fake Supabase client (no live DB)."""

from types import SimpleNamespace

import pytest

from dashboard.tickets import (
    TICKET_COLUMNS,
    TICKET_DETAIL_COLUMNS,
    ReassignError,
    get_ticket_detail,
    list_offices_for_department,
    list_routing_corrections,
    list_tickets,
    reassign_ticket,
    update_status,
)

CANNED_ROWS = [
    {
        "complaint_id": "SMD-0002",
        "status": "new",
        "department": "Jal Vibhag",
        "summary_en": "Issue: No water supply",
        "created_at": "2026-09-28T08:10:00+00:00",
        "updated_at": "2026-09-28T08:10:00+00:00",
        "offices": {"office_name": "Ward महात्मा गांधी Office", "level": "ward"},
    },
]


class _Query:
    """Generalised over S13's original single-table select/order/limit query -- S14 adds
    update/insert. One instance per `.table(...)` call, kept in `store.queries` so a test can
    inspect the exact call the function under test made (`store.queries[-1]`)."""

    def __init__(self, store, table_name):
        self.store = store
        self.table_name = table_name
        self.op: str | None = None
        self.payload: dict | None = None
        self.filters: dict = {}
        self.requested_columns: str | None = None
        self.order_calls: list[tuple[str, bool]] = []
        self.limit_n: int | None = None

    def select(self, columns):
        self.op = self.op or "select"
        self.requested_columns = columns
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def order(self, column, desc=False):
        self.order_calls.append((column, desc))
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def execute(self):
        rows = self.store.tables[self.table_name]
        if self.op == "insert":
            row = dict(self.payload)
            row.setdefault("id", len(rows) + 1)
            rows.append(row)
            self.store.inserted.setdefault(self.table_name, []).append(dict(row))
            return SimpleNamespace(data=[row])
        if self.op == "update":
            matched = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
            for r in matched:
                r.update(self.payload)
            self.store.updated.setdefault(self.table_name, []).append(
                (dict(self.filters), dict(self.payload))
            )
            return SimpleNamespace(data=matched)
        matched = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
        return SimpleNamespace(data=matched)


class FakeStore:
    """Duck-types as a `supabase.Client` (`.table(name)`), covering tickets/offices/
    routing_corrections. `queries` records every `_Query` created, newest last."""

    def __init__(self, **tables):
        self.tables = {name: list(rows) for name, rows in tables.items()}
        self.updated: dict[str, list] = {}
        self.inserted: dict[str, list] = {}
        self.queries: list[_Query] = []

    def table(self, name):
        query = _Query(self, name)
        self.queries.append(query)
        return query


# --- S13: list_tickets -------------------------------------------------------------------------


def test_list_tickets_requests_expected_shape():
    store = FakeStore(tickets=CANNED_ROWS)

    result = list_tickets(client=store)

    assert result == CANNED_ROWS
    query = store.queries[-1]
    assert query.requested_columns == TICKET_COLUMNS
    assert query.order_calls == [("created_at", True)]
    assert query.limit_n == 500


def test_list_tickets_never_selects_citizen_only_fields():
    for forbidden in ("fields", "original_text", "lat", "lng", "audio_path", "session_id"):
        assert forbidden not in TICKET_COLUMNS.split(",")


# --- S14: get_ticket_detail --------------------------------------------------------------------

DETAIL_ROW = {
    "id": 2,
    "complaint_id": "SMD-0002",
    "status": "new",
    "department": "Jal Vibhag",
    "office_id": 1,
    "fields": {"issue_type": "no_supply", "location": "वार्ड 1"},
    "summary_en": "Issue: No water supply",
    "original_text": "3 दिन से पानी नहीं आ रहा",
    "audio_path": None,
    "lat": None,
    "lng": None,
    "routing_confidence": 0.95,
    "created_at": "2026-09-28T08:10:00+00:00",
    "updated_at": "2026-09-28T08:10:00+00:00",
    "offices": {"office_name": "Ward महात्मा गांधी Office", "level": "ward"},
}


def test_get_ticket_detail_found():
    store = FakeStore(tickets=[DETAIL_ROW])

    assert get_ticket_detail("SMD-0002", client=store) == DETAIL_ROW
    assert store.queries[-1].requested_columns == TICKET_DETAIL_COLUMNS


def test_get_ticket_detail_not_found():
    store = FakeStore(tickets=[DETAIL_ROW])

    assert get_ticket_detail("SMD-9999", client=store) is None


def test_get_ticket_detail_requests_citizen_fields():
    for expected in ("fields", "original_text", "lat", "lng", "audio_path"):
        assert expected in TICKET_DETAIL_COLUMNS.split(",")


# --- S14: list_offices_for_department ------------------------------------------------------

OFFICES = [
    {"id": 1, "office_name": "Ward महात्मा गांधी Office", "level": "ward", "department": "Jal Vibhag", "code": "1", "active": True},
    {"id": 2, "office_name": "Ward रानी कमलापति Office", "level": "ward", "department": "Jal Vibhag", "code": "24", "active": True},
    {"id": 6, "office_name": "BMC Head Office", "level": "district", "department": "Jal Vibhag", "code": "BMC-HQ", "active": True},
    {"id": 9, "office_name": "Inactive Ward Office", "level": "ward", "department": "Jal Vibhag", "code": "99", "active": False},
    {"id": 20, "office_name": "Some Other Dept Office", "level": "ward", "department": "Other Dept", "code": "1", "active": True},
]


def test_list_offices_for_department_filters_active_and_department():
    store = FakeStore(offices=OFFICES)

    result = list_offices_for_department("Jal Vibhag", client=store)

    ids = {o["id"] for o in result}
    assert ids == {1, 2, 6}  # excludes the inactive row and the other department


# --- S14: update_status ------------------------------------------------------------------------


def test_update_status_writes_only_status():
    store = FakeStore(tickets=[dict(DETAIL_ROW)])

    update_status("SMD-0002", "in_progress", client=store)

    filters, payload = store.updated["tickets"][0]
    assert filters == {"complaint_id": "SMD-0002"}
    assert payload == {"status": "in_progress"}
    assert store.tables["tickets"][0]["status"] == "in_progress"


# --- S14: reassign_ticket ----------------------------------------------------------------------


def test_reassign_same_office_raises_before_any_call():
    store = FakeStore(tickets=[dict(DETAIL_ROW)], routing_corrections=[])

    with pytest.raises(ReassignError):
        reassign_ticket(ticket_id=2, from_office_id=1, to_office_id=1, reason=None, client=store)

    assert store.updated == {}
    assert store.inserted == {}


def test_reassign_updates_office_and_inserts_one_correction():
    store = FakeStore(tickets=[dict(DETAIL_ROW)], routing_corrections=[])

    reassign_ticket(ticket_id=2, from_office_id=1, to_office_id=6, reason="wrong ward", client=store)

    assert store.tables["tickets"][0]["office_id"] == 6
    assert len(store.inserted["routing_corrections"]) == 1
    correction = store.inserted["routing_corrections"][0]
    assert correction["ticket_id"] == 2
    assert correction["from_office_id"] == 1
    assert correction["to_office_id"] == 6
    assert correction["reason"] == "wrong ward"


# --- S14: list_routing_corrections ---------------------------------------------------------


def test_list_routing_corrections_orders_newest_first():
    rows = [
        {"ticket_id": 2, "from_office_id": 1, "to_office_id": 6, "reason": None, "created_at": "2026-09-27T10:00:00+00:00"},
    ]
    store = FakeStore(routing_corrections=rows)

    result = list_routing_corrections(2, client=store)

    assert result == rows
    query = store.queries[-1]
    assert query.filters == {"ticket_id": 2}
    assert query.order_calls == [("created_at", True)]
