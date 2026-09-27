"""S06 -- Session Manager (T14). Spec: docs/specs/S06-session-manager.md.

Owns the `sessions` and `messages` tables (S02): get-or-create with the 30-minute timeout (S01
D-A2), the (session_id, message_id) dedupe lookup (S01 section 8, S04 section 2 step 2), recent
history for the Turn Engine (S05), and the single end-of-turn write (S04 section 2 step 8).

Either of us can change this file. If you do, update docs/specs/S06-session-manager.md and tell
the other.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app import schemas
from app.db import get_client
from app.turn_engine import Message

SESSION_TIMEOUT_MINUTES = 30  # S01 section 8 / PROJECT.md section 6
UNIQUE_VIOLATION = "23505"  # Postgres error code for a PK/unique-constraint conflict


class SessionStatus(StrEnum):
    """Mirrors S02's session_status enum. EXPIRED is defined but never written -- staleness is
    always computed live from last_active_at (see get_or_create_session)."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class InputType(StrEnum):
    """Mirrors S02's messages.input_type CHECK constraint."""

    TEXT = "text"
    AUDIO = "audio"
    LOCATION = "location"


@dataclass(frozen=True)
class Session:
    """One-to-one with a `sessions` row (S02)."""

    id: uuid.UUID
    status: SessionStatus
    service_id: str | None
    collected_fields: dict[str, Any]
    awaiting_confirmation: bool
    lat: float | None
    lng: float | None
    created_at: datetime
    last_active_at: datetime


@dataclass(frozen=True)
class SessionUpdate:
    """What a turn leaves the session looking like -- passed into save_turn by the caller (T18).
    save_turn writes exactly this; it never auto-clears fields on a status change (S06 RULES 3)."""

    collected_fields: dict[str, Any]
    awaiting_confirmation: bool
    lat: float | None
    lng: float | None
    status: SessionStatus = SessionStatus.ACTIVE


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _default_fields() -> dict[str, Any]:
    """S02 default column values for a fresh/reset session row (no `id`)."""
    return {
        "status": SessionStatus.ACTIVE,
        "service_id": None,
        "collected_fields": {},
        "awaiting_confirmation": False,
        "lat": None,
        "lng": None,
    }


def _row_to_session(row: dict[str, Any]) -> Session:
    return Session(
        id=uuid.UUID(row["id"]),
        status=SessionStatus(row["status"]),
        service_id=row["service_id"],
        collected_fields=row["collected_fields"] or {},
        awaiting_confirmation=row["awaiting_confirmation"],
        lat=row["lat"],
        lng=row["lng"],
        created_at=datetime.fromisoformat(row["created_at"]),
        last_active_at=datetime.fromisoformat(row["last_active_at"]),
    )


def _maybe_single_data(result: Any) -> dict[str, Any] | None:
    """`.maybe_single().execute()` returns None outright on no match, not a response whose `.data`
    is None -- unlike every other query shape this module uses. Centralised here once."""
    return result.data if result is not None else None


def get_or_create_session(session_id: uuid.UUID, *, client: Client | None = None) -> Session:
    """S04 section 2 step 3 / S01 section 8, D-A2. Unknown id -> create. Stale (> 30 min) -> reset
    to fresh defaults under the same id, current message still processed, never a citizen error.
    Active, non-stale -> returned as read, no write."""
    client = client or get_client()
    existing = _maybe_single_data(
        client.table("sessions").select("*").eq("id", str(session_id)).maybe_single().execute()
    )

    if existing is None:
        row = {"id": str(session_id), **_default_fields(), "last_active_at": _now_iso()}
        inserted = client.table("sessions").insert(row).execute().data[0]
        return _row_to_session(inserted)

    last_active = datetime.fromisoformat(existing["last_active_at"])
    if datetime.now(UTC) - last_active > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
        row = {**_default_fields(), "last_active_at": _now_iso()}
        updated = client.table("sessions").update(row).eq("id", str(session_id)).execute().data[0]
        return _row_to_session(updated)

    return _row_to_session(existing)


def find_stored_response(
    session_id: uuid.UUID, message_id: uuid.UUID, *, client: Client | None = None
) -> schemas.MessageResponse | None:
    """S04 section 2 step 2 dedupe lookup. Read-only; never touches ASR, the LLM, or tickets."""
    client = client or get_client()
    row = _maybe_single_data(
        client.table("messages")
        .select("response")
        .eq("session_id", str(session_id))
        .eq("message_id", str(message_id))
        .maybe_single()
        .execute()
    )
    return None if row is None else schemas.MessageResponse.model_validate(row["response"])


def get_recent_messages(
    session_id: uuid.UUID, limit: int = 4, *, client: Client | None = None
) -> list[Message]:
    """Up to the last `limit` messages rows (turns) for this session, oldest first, unrolled into
    citizen/bot Message lines for the Turn Engine (S05 INPUT)."""
    client = client or get_client()
    rows = (
        client.table("messages")
        .select("text,transcript,response")
        .eq("session_id", str(session_id))
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data
    rows.reverse()  # oldest first

    result: list[Message] = []
    for row in rows:
        citizen_text = row["text"] or row["transcript"]
        if citizen_text:
            result.append(Message(role="citizen", text=citizen_text))
        result.append(Message(role="bot", text=row["response"]["reply_text"]))
    return result


def save_turn(
    *,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    input_type: InputType,
    text: str | None,
    transcript: str | None,
    audio_path: str | None,
    response: schemas.MessageResponse,
    session_update: SessionUpdate,
    client: Client | None = None,
) -> None:
    """S04 section 2 step 8, the single write at the end of a turn. `messages` is inserted before
    `sessions` is updated -- if the process dies in between, a retried message_id still hits the
    dedupe path (S01 section 8's whole point), even though session state may lag by one turn."""
    client = client or get_client()
    message_row = {
        "session_id": str(session_id),
        "message_id": str(message_id),
        "input_type": input_type,
        "text": text,
        "transcript": transcript,
        "audio_path": audio_path,
        "response": response.model_dump(mode="json"),
    }
    try:
        client.table("messages").insert(message_row).execute()
    except APIError as exc:
        if exc.code != UNIQUE_VIOLATION:
            raise  # a PK conflict here means another request already wrote this row first

    client.table("sessions").update(
        {
            "collected_fields": session_update.collected_fields,
            "awaiting_confirmation": session_update.awaiting_confirmation,
            "lat": session_update.lat,
            "lng": session_update.lng,
            "status": session_update.status,
            "last_active_at": _now_iso(),
        }
    ).eq("id", str(session_id)).execute()
