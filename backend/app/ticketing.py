"""S10 -- Ticket + routing (T17). Spec: docs/specs/S10-ticket-routing.md.
Also S11 -- Status lookup (T19). Spec: docs/specs/S11-status-lookup.md.

create_ticket is only reached once S07 (Validator) returns ready_to_submit (S04 section 2 step 7a).
Resolves jurisdiction (S09), decides new vs needs_review, and writes the tickets row. get_status is
the read-only counterpart: it lives here rather than a separate module since it's the read half of
the same tickets table (S11 SCOPE).

Either of us can change this file. If you do, update docs/specs/S10-ticket-routing.md /
docs/specs/S11-status-lookup.md and tell the other.
"""

import uuid
from typing import Any

from supabase import Client

from app import jurisdiction, schemas
from app.db import get_client
from app.service_spec import FieldSpec, LocationField, ServiceSpec


class TicketingError(RuntimeError):
    """A service spec has no `type: location` field -- a spec misconfiguration (S10 ERRORS)."""


def _find_location_field(spec: ServiceSpec) -> LocationField:
    for field in spec.fields:
        if field.type == "location":
            return field
    raise TicketingError(f"service {spec.service!r} has no location field")


def _is_present(
    field: FieldSpec, validated_fields: dict[str, Any], lat: float | None, lng: float | None
) -> bool:
    if field.type == "location":
        return (lat is not None and lng is not None) or field.name in validated_fields
    return field.name in validated_fields


def _display_value_en(
    field: FieldSpec, validated_fields: dict[str, Any], lat: float | None, lng: float | None
) -> str:
    if field.type == "location":
        if lat is not None and lng is not None:
            return f"{lat}, {lng}"
        return validated_fields[field.name]
    if field.type == "enum":
        return next(v.en for v in field.values if v.value == validated_fields[field.name])
    return str(validated_fields[field.name])


def _build_summary_en(
    spec: ServiceSpec, validated_fields: dict[str, Any], lat: float | None, lng: float | None
) -> str:
    """English summary for officers (S02 tickets.summary_en) -- from validated_fields and the
    spec's own .en labels, not from original_text (D-S10-2)."""
    parts = [
        f"{f.label.en}: {_display_value_en(f, validated_fields, lat, lng)}"
        for f in spec.fields
        if _is_present(f, validated_fields, lat, lng)
    ]
    return "; ".join(parts)


def create_ticket(
    *,
    session_id: uuid.UUID,
    spec: ServiceSpec,
    validated_fields: dict[str, Any],
    lat: float | None,
    lng: float | None,
    original_text: str,
    audio_path: str | None,
    client: Client | None = None,
) -> schemas.Ticket:
    client = client or get_client()
    location_field = _find_location_field(spec)

    match = jurisdiction.resolve_office(
        department=spec.department,
        lat=lat,
        lng=lng,
        place_name=validated_fields.get(location_field.name),
        max_match_distance_km=spec.routing.max_match_distance_km,
        client=client,
    )

    status = (
        schemas.ComplaintStatus.NEEDS_REVIEW
        if match.confidence < spec.routing.min_confidence or match.matched_via == "fallback"
        else schemas.ComplaintStatus.NEW
    )
    summary_en = _build_summary_en(spec, validated_fields, lat, lng)

    row = (
        client.table("tickets")
        .insert(
            {
                "session_id": str(session_id),
                "service_id": spec.service,
                "department": spec.department,
                "office_id": match.office.id,
                "status": status,
                "fields": validated_fields,
                "summary_en": summary_en,
                "original_text": original_text,
                "audio_path": audio_path,
                "lat": lat,
                "lng": lng,
                "routing_confidence": match.confidence,
            }
        )
        .execute()
        .data[0]
    )

    return schemas.Ticket(
        complaint_id=row["complaint_id"],
        department=spec.department,
        office=schemas.Office(name=match.office.office_name, level=match.office.level),
        status=status,
    )


def get_status(complaint_id: str, *, client: Client | None = None) -> dict[str, Any] | None:
    """S11: status/department/updated_at only -- never fields, original_text, lat/lng, audio_path
    (S01 section 5, S11 RULES 2)."""
    client = client or get_client()
    rows = (
        client.table("tickets")
        .select("status,department,updated_at")
        .eq("complaint_id", complaint_id)
        .execute()
    ).data
    return rows[0] if rows else None
