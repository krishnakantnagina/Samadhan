"""S31 in the dashboard queries: the new columns are read when the database has them, and an older database falls back instead of breaking."""

from types import SimpleNamespace

from dashboard import tickets


class FakeQuery:
    def __init__(self, owner):
        self.owner, self.cols = owner, None

    def select(self, cols):
        self.cols = cols
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def eq(self, *a):
        return self

    def execute(self):
        self.owner.calls.append(self.cols)
        if self.owner.old_schema and ("district" in self.cols or "users(" in self.cols):
            raise RuntimeError("column tickets.district does not exist")
        row = {"complaint_id": "SMD-0001"}
        if "district" in self.cols:
            row.update(district="Rewa", tehsil="Mauganj", users={"phone": "+919876543210"})
        return SimpleNamespace(data=[row])


class FakeClient:
    def __init__(self, old_schema):
        self.old_schema, self.calls = old_schema, []

    def table(self, name):
        return FakeQuery(self)


def test_a_current_database_returns_the_new_columns_and_the_phone_only_for_the_opened_ticket():
    listing = FakeClient(old_schema=False)
    assert tickets.list_tickets(client=listing)[0]["district"] == "Rewa"
    assert "users(" not in listing.calls[0]  # the phone is never in the list query
    detail_client = FakeClient(old_schema=False)
    detail = tickets.get_ticket_detail("SMD-0001", client=detail_client)
    assert detail["users"]["phone"] == "+919876543210" and "users(phone)" in detail_client.calls[0]


def test_an_older_database_falls_back_to_the_base_columns_instead_of_failing():
    client = FakeClient(old_schema=True)
    assert tickets.list_tickets(client=client) == [{"complaint_id": "SMD-0001"}]
    assert client.calls == [tickets.TICKET_COLUMNS + tickets.LIST_EXTRA_COLUMNS, tickets.TICKET_COLUMNS]
    detail_client = FakeClient(old_schema=True)
    assert tickets.get_ticket_detail("SMD-0001", client=detail_client) == {"complaint_id": "SMD-0001"}
    assert detail_client.calls[-1] == tickets.TICKET_DETAIL_COLUMNS


def test_the_list_never_selects_citizen_contact_details():
    assert "phone" not in tickets.TICKET_COLUMNS and "phone" not in tickets.LIST_EXTRA_COLUMNS
