"""S13 -- dashboard/tickets.py against a minimal fake Supabase client (no live DB)."""

from types import SimpleNamespace

from dashboard.tickets import TICKET_COLUMNS, list_tickets

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
    def __init__(self, rows):
        self._rows = rows
        self.requested_columns: str | None = None
        self.order_col: str | None = None
        self.order_desc: bool | None = None
        self.limit_n: int | None = None

    def select(self, columns):
        self.requested_columns = columns
        return self

    def order(self, column, desc=False):
        self.order_col = column
        self.order_desc = desc
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows)


class FakeClient:
    def __init__(self, rows):
        self.query = _Query(rows)

    def table(self, name):
        assert name == "tickets"
        return self.query


def test_list_tickets_requests_expected_shape():
    client = FakeClient(CANNED_ROWS)
    result = list_tickets(client=client)

    assert result == CANNED_ROWS
    assert client.query.requested_columns == TICKET_COLUMNS
    assert client.query.order_col == "created_at"
    assert client.query.order_desc is True
    assert client.query.limit_n == 500


def test_list_tickets_never_selects_citizen_only_fields():
    for forbidden in ("fields", "original_text", "lat", "lng", "audio_path", "session_id"):
        assert forbidden not in TICKET_COLUMNS.split(",")
