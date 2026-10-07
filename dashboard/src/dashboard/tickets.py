"""S13 -- Dashboard ticket list (T23). S14 -- detail, status, reassign, review queue (T24).
Spec: docs/specs/S13-dashboard-auth-list.md, docs/specs/S14-dashboard-detail-actions.md.

The dashboard writes exactly tickets.status, tickets.office_id, and inserts routing_corrections
rows -- nothing else, ever (S02 RULES 3). Every write in this module is one of those two.
"""

import logging
from typing import Any

from supabase import Client

from dashboard.db import get_client

logger = logging.getLogger(__name__)

# Never select("*") -- same posture as backend's S11 get_status: no citizen-only fields
# (fields, original_text, lat/lng, audio_path, session_id) leak into the list view.
TICKET_COLUMNS = (
    "complaint_id,status,department,summary_en,created_at,updated_at,offices(office_name,level)"
)

# Unlike TICKET_COLUMNS, this *does* include citizen fields -- a deliberately opened single ticket
# is exactly where they belong (S14 DATA ACCESS).
TICKET_DETAIL_COLUMNS = (
    "id,complaint_id,service_id,status,department,office_id,fields,summary_en,original_text,"
    "audio_path,lat,lng,routing_confidence,created_at,updated_at,offices(office_name,level)"
)


# S31: columns added by database/migrations/002. Read when present; a database that has not run the migration yet answers with an error and we fall back to the
# base columns, so the dashboard never breaks on an older schema. The citizen's phone is selected ONLY for one deliberately opened ticket (the officer calls back).
LIST_EXTRA_COLUMNS = ",district,tehsil,location_precision"
DETAIL_EXTRA_COLUMNS = ",district,tehsil,nearest_place,location_precision,users(phone)"


def _with_fallback(run, columns: str, extra: str):
    """run(columns) with the S31 extras first; on any database error (missing column or table) run it again with the base columns."""
    try:
        return run(columns + extra)
    except Exception:  # noqa: BLE001 -- postgrest APIError for an unknown column/relation
        return run(columns)


# S24 section 4: the map's own column list. Adds lat/lng (the list view deliberately omits them) and
# `fields` (issue label / location text); still never original_text, audio_path or session_id.
MAP_COLUMNS = "complaint_id,service_id,status,department,fields,lat,lng,created_at,offices(office_name)"


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


def count_tickets(*, client: Client | None = None) -> int | None:
    """How many tickets exist in all (the list views load only the newest 500). None if the count could not be read."""
    try:
        result = (client or get_client()).table("tickets").select("id", count="exact").limit(1).execute()
        return int(result.count) if result.count is not None else None
    except Exception:  # noqa: BLE001 -- a count is only used for a warning banner
        return None


def truncation_notice(loaded: int, total: int | None) -> str | None:
    """Words for the banner when the list is shorter than the table, else None. KPIs, overdue counts and the map are computed from the loaded rows only."""
    if total is None or total <= loaded:
        return None
    return (
        f"Showing the newest {loaded} of {total} tickets. The totals, overdue counts, charts and map below cover only these {loaded}. "
        "Older tickets are not in this view yet."
    )


def list_tickets(*, client: Client | None = None) -> list[dict[str, Any]]:
    """Up to 500 tickets, newest first, joined to their office's name/level (S13 BEHAVIOR 1)."""
    client = client or get_client()
    return _with_fallback(
        lambda cols: client.table("tickets").select(cols).order("created_at", desc=True).limit(500).execute().data, TICKET_COLUMNS, LIST_EXTRA_COLUMNS
    )


def get_ticket_detail(complaint_id: str, *, client: Client | None = None) -> dict[str, Any] | None:
    """One ticket, every column an officer reviewing it needs (S14 BEHAVIOR 2)."""
    client = client or get_client()
    rows = _with_fallback(
        lambda cols: client.table("tickets").select(cols).eq("complaint_id", complaint_id).execute().data, TICKET_DETAIL_COLUMNS, DETAIL_EXTRA_COLUMNS
    )
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


def list_all_offices(*, client: Client | None = None) -> list[dict[str, Any]]:
    """Active offices of EVERY department, for the reassign dropdown (S28 4.4): a ticket sent to the
    wrong department is corrected by moving it to an office of the right one."""
    client = client or get_client()
    return (
        client.table("offices")
        .select("id,department,office_name,level")
        .eq("active", True)
        .order("department")
        .order("level")
        .order("code")
        .execute()
    ).data


def record_event(complaint_id: str, actor: str, action: str, detail: str | None = None, *, client: Client | None = None) -> None:
    """Audit trail (migration 006): who did what to which ticket. Never raises: a missing table or a database hiccup must not block the officer's action."""
    try:
        (client or get_client()).table("ticket_events").insert(
            {"complaint_id": complaint_id, "actor": actor or "unknown", "action": action, "detail": detail}
        ).execute()
    except Exception as exc:  # noqa: BLE001 -- postgrest APIError (table missing) or network
        logger.warning("audit event not recorded (apply database/migrations/006): %s", exc.__class__.__name__)


def list_events(complaint_id: str, *, limit: int = 20, client: Client | None = None) -> list[dict[str, Any]]:
    """This ticket's audit trail, newest first. Empty when the table does not exist yet."""
    try:
        return (
            (client or get_client())
            .table("ticket_events")
            .select("actor,action,detail,created_at")
            .eq("complaint_id", complaint_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ).data
    except Exception:  # noqa: BLE001 -- table missing on an older database
        return []


def update_status(
    complaint_id: str, new_status: str, *, actor: str | None = None, previous: str | None = None, client: Client | None = None
) -> None:
    """Only column touched: status. updated_at is tickets' own BEFORE UPDATE trigger (T03) --
    this function never sets it (S14 RULES 4). With `actor` the change is also written to the audit trail."""
    client = client or get_client()
    client.table("tickets").update({"status": new_status}).eq("complaint_id", complaint_id).execute()
    if actor:
        record_event(complaint_id, actor, "status_changed", f"{previous or '?'} -> {new_status}", client=client)


class ReassignError(ValueError):
    """Reassign to the same office -- rejected here, before it ever reaches the DB (S02 ERRORS)."""


def reassign_ticket(
    *,
    ticket_id: int,
    from_office_id: int,
    to_office_id: int,
    reason: str | None,
    actor: str | None = None,
    complaint_id: str | None = None,
    client: Client | None = None,
) -> None:
    """Updates tickets.office_id and inserts one routing_corrections row (S02 ACCEPTANCE). Two
    sequential calls, not one transaction (S14 D-S14-2) -- no RPC-based transaction exists
    anywhere in this project yet; disproportionate to add for one hackathon-scale ticket."""
    if from_office_id == to_office_id:
        raise ReassignError("Cannot reassign a ticket to the office it's already at.")
    client = client or get_client()
    update: dict[str, Any] = {"office_id": to_office_id}
    # S28 4.4: moving to another department's office also moves the ticket's department (the status page
    # and dashboard filters read tickets.department). service_id and fields keep the original record.
    target = client.table("offices").select("department").eq("id", to_office_id).execute().data
    if target and target[0].get("department"):
        update["department"] = target[0]["department"]
    client.table("tickets").update(update).eq("id", ticket_id).execute()
    client.table("routing_corrections").insert(
        {
            "ticket_id": ticket_id,
            "from_office_id": from_office_id,
            "to_office_id": to_office_id,
            "reason": reason,
        }
    ).execute()
    if actor and complaint_id:
        record_event(complaint_id, actor, "reassigned", f"office {from_office_id} -> {to_office_id}" + (f": {reason}" if reason else ""), client=client)


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
