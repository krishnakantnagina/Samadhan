"""S13 -- Dashboard ticket list (T23). S14 -- detail, status, reassign, review queue (T24).
Spec: docs/specs/S13-dashboard-auth-list.md, docs/specs/S14-dashboard-detail-actions.md.

The dashboard writes exactly tickets.status, tickets.office_id, and inserts routing_corrections
rows -- nothing else, ever (S02 RULES 3). Every write in this module is one of those two.
"""

from typing import Any

from supabase import Client

from dashboard.db import get_client

# Never select("*") -- same posture as backend's S11 get_status: no citizen-only fields
# (fields, original_text, lat/lng, audio_path, session_id) leak into the list view.
TICKET_COLUMNS = (
    "complaint_id,status,department,summary_en,created_at,updated_at,offices(office_name,level)"
)

# Unlike TICKET_COLUMNS, this *does* include citizen fields -- a deliberately opened single ticket
# is exactly where they belong (S14 DATA ACCESS).
TICKET_DETAIL_COLUMNS = (
    "id,complaint_id,status,department,office_id,fields,summary_en,original_text,"
    "audio_path,lat,lng,routing_confidence,created_at,updated_at,offices(office_name,level)"
)


# S24 section 4: the map's own column list. Adds lat/lng (the list view deliberately omits them) and
# `fields` (issue label / location text); still never original_text, audio_path or session_id.
MAP_COLUMNS = "complaint_id,status,department,fields,lat,lng,created_at,offices(office_name)"


def list_map_points(*, client: Client | None = None) -> list[dict[str, Any]]:
    """Up to 500 tickets with the columns the map needs, newest first (S24 section 4). Read-only."""
    client = client or get_client()
    return (
        client.table("tickets")
        .select(MAP_COLUMNS)
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    ).data


def list_tickets(*, client: Client | None = None) -> list[dict[str, Any]]:
    """Up to 500 tickets, newest first, joined to their office's name/level (S13 BEHAVIOR 1)."""
    client = client or get_client()
    return (
        client.table("tickets")
        .select(TICKET_COLUMNS)
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    ).data


def get_ticket_detail(complaint_id: str, *, client: Client | None = None) -> dict[str, Any] | None:
    """One ticket, every column an officer reviewing it needs (S14 BEHAVIOR 2)."""
    client = client or get_client()
    rows = (
        client.table("tickets")
        .select(TICKET_DETAIL_COLUMNS)
        .eq("complaint_id", complaint_id)
        .execute()
    ).data
    return rows[0] if rows else None


def list_offices_for_department(
    department: str, *, client: Client | None = None
) -> list[dict[str, Any]]:
    """Active offices for one department, for the reassign dropdown (S14 BEHAVIOR 4)."""
    client = client or get_client()
    return (
        client.table("offices")
        .select("id,office_name,level")
        .eq("department", department)
        .eq("active", True)
        .order("level")
        .order("code")
        .execute()
    ).data


def update_status(complaint_id: str, new_status: str, *, client: Client | None = None) -> None:
    """Only column touched: status. updated_at is tickets' own BEFORE UPDATE trigger (T03) --
    this function never sets it (S14 RULES 4)."""
    client = client or get_client()
    client.table("tickets").update({"status": new_status}).eq("complaint_id", complaint_id).execute()


class ReassignError(ValueError):
    """Reassign to the same office -- rejected here, before it ever reaches the DB (S02 ERRORS)."""


def reassign_ticket(
    *,
    ticket_id: int,
    from_office_id: int,
    to_office_id: int,
    reason: str | None,
    client: Client | None = None,
) -> None:
    """Updates tickets.office_id and inserts one routing_corrections row (S02 ACCEPTANCE). Two
    sequential calls, not one transaction (S14 D-S14-2) -- no RPC-based transaction exists
    anywhere in this project yet; disproportionate to add for one hackathon-scale ticket."""
    if from_office_id == to_office_id:
        raise ReassignError("Cannot reassign a ticket to the office it's already at.")
    client = client or get_client()
    client.table("tickets").update({"office_id": to_office_id}).eq("id", ticket_id).execute()
    client.table("routing_corrections").insert(
        {
            "ticket_id": ticket_id,
            "from_office_id": from_office_id,
            "to_office_id": to_office_id,
            "reason": reason,
        }
    ).execute()


def list_routing_corrections(
    ticket_id: int, *, client: Client | None = None
) -> list[dict[str, Any]]:
    """This ticket's reassignment history, newest first (S14 BEHAVIOR 2)."""
    client = client or get_client()
    return (
        client.table("routing_corrections")
        .select("from_office_id,to_office_id,reason,created_at")
        .eq("ticket_id", ticket_id)
        .order("created_at", desc=True)
        .execute()
    ).data
