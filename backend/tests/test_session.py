"""S06 Session Manager (T14): every function/branch against a fake Supabase client -- no network,
no real credentials. FakeSupabaseClient implements only the chained-builder calls app/session.py
actually makes.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from postgrest.exceptions import APIError

from app import schemas
from app.session import (
    InputType,
    SessionStatus,
    SessionUpdate,
    find_stored_response,
    get_or_create_session,
    get_recent_messages,
    save_turn,
)

# --- Fake Supabase client ----------------------------------------------------------------------


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, fake, table_name):
        self.fake = fake
        self.table_name = table_name
        self.op = None
        self.payload = None
        self.filters: dict = {}
        self.order_col = None
        self.order_desc = False
        self.limit_n = None
        self.single = False
        self.select_cols: tuple = ()

    def select(self, *cols):
        self.op = "select"
        self.select_cols = cols
        return self

    def insert(self, row):
        self.op = "insert"
        self.payload = row
        return self

    def update(self, row):
        self.op = "update"
        self.payload = row
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def order(self, column, *, desc=False):
        self.order_col = column
        self.order_desc = desc
        return self

    def limit(self, size):
        self.limit_n = size
        return self

    def maybe_single(self):
        self.single = True
        return self

    def _matches(self, row):
        return all(row.get(k) == v for k, v in self.filters.items())

    def execute(self):
        store = self.fake.tables[self.table_name]

        if self.op == "insert":
            self.fake._check_unique(self.table_name, self.payload)
            row = dict(self.payload)
            row.setdefault("created_at", iso(datetime.now(UTC)))  # S02 DEFAULT now()
            store.append(row)
            self.fake.calls.append(("insert", self.table_name))
            return _Response([dict(row)])

        if self.op == "update":
            matched = [r for r in store if self._matches(r)]
            for r in matched:
                r.update(self.payload)
            self.fake.calls.append(("update", self.table_name))
            return _Response([dict(r) for r in matched])

        matched = [dict(r) for r in store if self._matches(r)]
        if self.order_col:
            matched.sort(key=lambda r: r[self.order_col], reverse=self.order_desc)
        if self.limit_n is not None:
            matched = matched[: self.limit_n]
        if self.select_cols and self.select_cols != ("*",):
            cols = [c for group in self.select_cols for c in group.split(",")]
            matched = [{c: r[c] for c in cols} for r in matched]
        self.fake.calls.append(("select", self.table_name))

        if self.single:
            return None if not matched else _Response(matched[0])
        return _Response(matched)


class FakeSupabaseClient:
    UNIQUE_KEYS: ClassVar[dict[str, tuple[str, ...]]] = {
        "sessions": ("id",),
        "messages": ("session_id", "message_id"),
    }

    def __init__(self):
        self.tables: dict[str, list[dict]] = {"sessions": [], "messages": []}
        self.calls: list[tuple[str, str]] = []

    def table(self, name):
        return _Query(self, name)

    def _check_unique(self, table_name, row):
        keys = self.UNIQUE_KEYS.get(table_name, ())
        for existing in self.tables[table_name]:
            if all(existing.get(k) == row.get(k) for k in keys):
                raise APIError({"code": "23505", "message": "duplicate key value"})


# --- Helpers -----------------------------------------------------------------------------------


def iso(dt: datetime) -> str:
    return dt.isoformat()


def seed_session(fake: FakeSupabaseClient, session_id: uuid.UUID, **overrides) -> dict:
    now = datetime.now(UTC)
    row = {
        "id": str(session_id),
        "status": SessionStatus.ACTIVE,
        "service_id": None,
        "collected_fields": {},
        "awaiting_confirmation": False,
        "lat": None,
        "lng": None,
        "created_at": iso(now),
        "last_active_at": iso(now),
    }
    row.update(overrides)
    fake.tables["sessions"].append(row)
    return row


def seed_message(fake: FakeSupabaseClient, **overrides) -> dict:
    row = {
        "session_id": str(uuid.uuid4()),
        "message_id": str(uuid.uuid4()),
        "input_type": InputType.TEXT,
        "text": None,
        "transcript": None,
        "audio_path": None,
        "response": {"reply_text": "ok"},
        "created_at": iso(datetime.now(UTC)),
    }
    row.update(overrides)
    fake.tables["messages"].append(row)
    return row


def make_response(session_id, message_id, **overrides) -> schemas.MessageResponse:
    defaults = {
        "session_id": session_id,
        "message_id": message_id,
        "action": schemas.Action.ASK,
        "ask_for": "location",
        "reply_text": "reply",
        "transcript": None,
        "summary": None,
        "ticket": None,
        "duplicate": False,
    }
    defaults.update(overrides)
    return schemas.MessageResponse(**defaults)


# --- get_or_create_session -----------------------------------------------------------------------


def test_get_or_create_session_creates_new():
    fake = FakeSupabaseClient()
    session_id = uuid.uuid4()

    session = get_or_create_session(session_id, client=fake)

    assert session.id == session_id
    assert session.status == SessionStatus.ACTIVE
    assert session.service_id is None
    assert session.collected_fields == {}
    assert session.awaiting_confirmation is False
    assert session.lat is None
    assert session.lng is None
    assert len(fake.tables["sessions"]) == 1
    assert ("insert", "sessions") in fake.calls


def test_get_or_create_session_returns_active_unchanged():
    fake = FakeSupabaseClient()
    session_id = uuid.uuid4()
    seed_session(
        fake,
        session_id,
        service_id="water_supply",
        collected_fields={"issue_type": "no_supply"},
        awaiting_confirmation=True,
        last_active_at=iso(datetime.now(UTC) - timedelta(minutes=5)),
    )

    session = get_or_create_session(session_id, client=fake)

    assert session.service_id == "water_supply"
    assert session.collected_fields == {"issue_type": "no_supply"}
    assert session.awaiting_confirmation is True
    assert ("update", "sessions") not in fake.calls


def test_get_or_create_session_resets_stale():
    fake = FakeSupabaseClient()
    session_id = uuid.uuid4()
    seed_session(
        fake,
        session_id,
        service_id="water_supply",
        collected_fields={"issue_type": "no_supply"},
        awaiting_confirmation=True,
        lat=23.25,
        lng=77.41,
        last_active_at=iso(datetime.now(UTC) - timedelta(minutes=31)),
    )

    session = get_or_create_session(session_id, client=fake)

    assert session.id == session_id
    assert session.service_id is None
    assert session.collected_fields == {}
    assert session.awaiting_confirmation is False
    assert session.lat is None
    assert session.lng is None
    assert datetime.now(UTC) - session.last_active_at < timedelta(seconds=5)


def test_get_or_create_session_reuses_completed_row_as_is():
    fake = FakeSupabaseClient()
    session_id = uuid.uuid4()
    seed_session(
        fake,
        session_id,
        status=SessionStatus.COMPLETED,
        last_active_at=iso(datetime.now(UTC) - timedelta(minutes=2)),
    )

    session = get_or_create_session(session_id, client=fake)

    assert session.status == SessionStatus.COMPLETED
    assert ("update", "sessions") not in fake.calls


# --- find_stored_response ------------------------------------------------------------------------


def test_find_stored_response_found():
    fake = FakeSupabaseClient()
    session_id, message_id = uuid.uuid4(), uuid.uuid4()
    response = make_response(session_id, message_id, action=schemas.Action.CONFIRM)
    seed_message(
        fake,
        session_id=str(session_id),
        message_id=str(message_id),
        response=response.model_dump(mode="json"),
    )

    found = find_stored_response(session_id, message_id, client=fake)

    assert found == response


def test_find_stored_response_not_found():
    fake = FakeSupabaseClient()
    assert find_stored_response(uuid.uuid4(), uuid.uuid4(), client=fake) is None


# --- get_recent_messages -------------------------------------------------------------------------


def test_get_recent_messages_unrolls_citizen_and_bot_oldest_first():
    fake = FakeSupabaseClient()
    session_id = uuid.uuid4()
    base = datetime.now(UTC)
    seed_message(
        fake,
        session_id=str(session_id),
        text="no water",
        response={"reply_text": "which ward?"},
        created_at=iso(base - timedelta(minutes=2)),
    )
    seed_message(
        fake,
        session_id=str(session_id),
        text="ward 12",
        response={"reply_text": "confirm?"},
        created_at=iso(base - timedelta(minutes=1)),
    )

    messages = get_recent_messages(session_id, client=fake)

    assert [(m.role, m.text) for m in messages] == [
        ("citizen", "no water"),
        ("bot", "which ward?"),
        ("citizen", "ward 12"),
        ("bot", "confirm?"),
    ]


def test_get_recent_messages_skips_citizen_line_when_no_text():
    fake = FakeSupabaseClient()
    session_id = uuid.uuid4()
    seed_message(
        fake,
        session_id=str(session_id),
        text=None,
        transcript=None,
        response={"reply_text": "ticket submitted"},
    )

    messages = get_recent_messages(session_id, client=fake)

    assert [(m.role, m.text) for m in messages] == [("bot", "ticket submitted")]


def test_get_recent_messages_respects_limit():
    fake = FakeSupabaseClient()
    session_id = uuid.uuid4()
    base = datetime.now(UTC)
    for i in range(6):
        seed_message(
            fake,
            session_id=str(session_id),
            text=f"turn {i}",
            response={"reply_text": f"reply {i}"},
            created_at=iso(base - timedelta(minutes=6 - i)),
        )

    messages = get_recent_messages(session_id, limit=4, client=fake)

    citizen_lines = [m.text for m in messages if m.role == "citizen"]
    assert citizen_lines == ["turn 2", "turn 3", "turn 4", "turn 5"]


# --- save_turn -------------------------------------------------------------------------------------


def test_save_turn_writes_message_then_updates_session_in_order():
    fake = FakeSupabaseClient()
    session_id, message_id = uuid.uuid4(), uuid.uuid4()
    seed_session(fake, session_id)
    response = make_response(session_id, message_id, action=schemas.Action.CONFIRM)

    save_turn(
        session_id=session_id,
        message_id=message_id,
        input_type=InputType.TEXT,
        text="ward 12",
        transcript=None,
        audio_path=None,
        response=response,
        session_update=SessionUpdate(
            collected_fields={"location": "ward 12"},
            awaiting_confirmation=True,
            lat=None,
            lng=None,
        ),
        client=fake,
    )

    assert fake.calls == [("insert", "messages"), ("update", "sessions")]
    [message_row] = fake.tables["messages"]
    assert message_row["response"]["action"] == "confirm"
    [session_row] = fake.tables["sessions"]
    assert session_row["collected_fields"] == {"location": "ward 12"}
    assert session_row["awaiting_confirmation"] is True


def test_save_turn_duplicate_message_insert_is_a_noop():
    fake = FakeSupabaseClient()
    session_id, message_id = uuid.uuid4(), uuid.uuid4()
    seed_session(fake, session_id)
    response = make_response(session_id, message_id)
    seed_message(fake, session_id=str(session_id), message_id=str(message_id))

    save_turn(
        session_id=session_id,
        message_id=message_id,
        input_type=InputType.TEXT,
        text="ward 12",
        transcript=None,
        audio_path=None,
        response=response,
        session_update=SessionUpdate(
            collected_fields={}, awaiting_confirmation=False, lat=None, lng=None
        ),
        client=fake,
    )

    assert len(fake.tables["messages"]) == 1
    assert ("update", "sessions") in fake.calls
