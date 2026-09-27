"""S13 -- Dashboard ticket list (T23). Spec: docs/specs/S13-dashboard-auth-list.md.

Read-only. Never writes to tickets/offices/routing_corrections -- that's T24 (S02 RULES 3).
"""

from typing import Any

from supabase import Client

from dashboard.db import get_client

# Never select("*") -- same posture as backend's S11 get_status: no citizen-only fields
# (fields, original_text, lat/lng, audio_path, session_id) leak into the list view.
TICKET_COLUMNS = (
    "complaint_id,status,department,summary_en,created_at,updated_at,offices(office_name,level)"
)


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
