"""S10 -- Ticket + routing (T17). Spec: docs/specs/S10-ticket-routing.md.
Also S11 -- Status lookup (T19). Spec: docs/specs/S11-status-lookup.md.

create_ticket is only reached once S07 (Validator) returns ready_to_submit (S04 section 2 step 7a).
Resolves jurisdiction (S09), decides new vs needs_review, and writes the tickets row. get_status is
the read-only counterpart: it lives here rather than a separate module since it's the read half of
the same tickets table (S11 SCOPE).

Either of us can change this file. If you do, update docs/specs/S10-ticket-routing.md /
docs/specs/S11-status-lookup.md and tell the other.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from supabase import Client

from app import district_geo, jurisdiction, schemas
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


logger = logging.getLogger(__name__)
HUMAN_EVALUATION_DEPARTMENT = "Human Evaluation"  # the queue desk (offices.department); see jurisdiction.LEGACY_DEPARTMENTS
INTAKE_META_KEY = "_intake"  # S30: notes kept by app/intake.py inside the ticket's fields
NEW_COLUMNS = ("district", "tehsil", "nearest_place", "location_precision", "user_id")  # S31 migration 002; absent in older databases


def _location_columns(
    validated_fields: dict[str, Any], location_name: str, lat: float | None, lng: float | None, district: str | None = None
) -> dict[str, Any]:
    """Structured location columns from the intake notes (S31). Only when intake v2 wrote notes, or when a GPS point gave a district; precision: exact (GPS) > village (a named
    place and a district) > district > unknown. `district` is the one routing used (typed by the citizen, else found from their GPS point)."""
    meta = validated_fields.get(INTAKE_META_KEY)
    has_gps = lat is not None and lng is not None
    if not meta:
        return {"district": district, "location_precision": "exact"} if has_gps and district else {}
    loc = meta.get("location_details") or {}
    district = loc.get("district") or district
    precision = "exact" if has_gps else "village" if (validated_fields.get(location_name) and district) else "district" if district else "unknown"
    return {"district": district, "tehsil": loc.get("tehsil"), "nearest_place": loc.get("nearest_place"), "location_precision": precision}


def _district_of(validated_fields: dict[str, Any]) -> str | None:
    """The citizen's district (English name) from the intake notes (app/location_details.py), or None when they did not give one."""
    loc = (validated_fields.get(INTAKE_META_KEY) or {}).get("location_details") or {}
    return loc.get("district") or None


DUPLICATE_WINDOW_SECONDS = 180  # the same complaint, same chat, within this long = the same ticket (a double tap or a retry after a timeout)


def _age_seconds(created_at: Any) -> float | None:
    try:
        created = datetime.fromisoformat(str(created_at))
        return (datetime.now(UTC) - (created if created.tzinfo else created.replace(tzinfo=UTC))).total_seconds()
    except ValueError:
        return None


def _existing_ticket(client: Client, session_id: uuid.UUID, spec: ServiceSpec, original_text: str) -> schemas.Ticket | None:
    """A ticket this chat session already filed for the same complaint a moment ago, as the same response (audit M1). Fail-open: any doubt means "no duplicate"
    and a new ticket is filed (a lost complaint is worse than a repeated one). The website makes a new message id for every try, so the message-id dedupe
    never catches a double tap; this does."""
    try:
        rows = (
            client.table("tickets")
            .select("complaint_id,status,office_id,created_at")
            .eq("session_id", str(session_id))
            .eq("service_id", spec.service)
            .eq("original_text", original_text)
            .execute()
        ).data
        fresh = [r for r in rows if (_age_seconds(r["created_at"]) or 1e9) <= DUPLICATE_WINDOW_SECONDS]
        if not fresh:
            return None
        row = max(fresh, key=lambda r: str(r["created_at"]))
        office = client.table("offices").select("office_name,level").eq("id", row["office_id"]).execute().data[0]
        return schemas.Ticket(
            complaint_id=row["complaint_id"],
            department=spec.department,
            office=schemas.Office(name=office["office_name"], level=office["level"]),
            status=row["status"],
        )
    except Exception:  # noqa: BLE001 -- never block filing on a duplicate check
        return None


def _insert_ticket(client: Client, row: dict[str, Any]) -> dict[str, Any]:
    """Insert the ticket. If the database does not have the S31 columns yet (migration 002 not applied) retry without them: a complaint is never lost to a missing column."""
    try:
        return client.table("tickets").insert(row).execute().data[0]
    except Exception as exc:
        message = str(exc).lower()
        if not any(col in row for col in NEW_COLUMNS) or not ("column" in message or "schema cache" in message):
            raise
        logger.warning("tickets insert without the S31 columns (apply database/migrations/002): %s", exc.__class__.__name__)
        return client.table("tickets").insert({k: v for k, v in row.items() if k not in NEW_COLUMNS}).execute().data[0]


def create_ticket(
    *,
    session_id: uuid.UUID,
    spec: ServiceSpec,
    validated_fields: dict[str, Any],
    lat: float | None,
    lng: float | None,
    original_text: str,
    audio_path: str | None,
    user_id: uuid.UUID | str | None = None,
    client: Client | None = None,
) -> schemas.Ticket:
    client = client or get_client()
    location_field = _find_location_field(spec)

    already = _existing_ticket(client, session_id, spec, original_text)
    if already is not None:
        logger.info("duplicate submit for %s: returning the existing ticket", already.complaint_id)
        return already

    district = _district_of(validated_fields) or (district_geo.district_for(lat, lng) if lat is not None and lng is not None else None)
    try:
        match = jurisdiction.resolve_office(
            department=spec.department,
            lat=lat,
            lng=lng,
            place_name=validated_fields.get(location_field.name),
            max_match_distance_km=spec.routing.max_match_distance_km,
            district=district,
            client=client,
        )
        no_desk = False
    except jurisdiction.JurisdictionError:
        # This department has no office in the database yet (a spec exists before its offices do). A citizen's complaint is never lost to missing data:
        # it goes to the Human Evaluation desk, marked for review, and a person assigns it.
        logger.warning("no office for department %r: routing the complaint to Human Evaluation", spec.department)
        match = jurisdiction.resolve_office(
            department=HUMAN_EVALUATION_DEPARTMENT, lat=None, lng=None, place_name=None, max_match_distance_km=spec.routing.max_match_distance_km, client=client
        )
        no_desk = True

    status = (
        schemas.ComplaintStatus.NEEDS_REVIEW
        if no_desk or match.confidence < spec.routing.min_confidence or match.matched_via == "fallback"
        else schemas.ComplaintStatus.NEW
    )
    summary_en = _build_summary_en(spec, validated_fields, lat, lng)

    new_row = {
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
        **_location_columns(validated_fields, location_field.name, lat, lng, district),
    }
    if user_id is not None:
        new_row["user_id"] = str(user_id)  # S31: the registered citizen (phone) who filed it; the officer calls back on this number
    row = _insert_ticket(client, new_row)

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
