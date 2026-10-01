"""S09 -- Jurisdiction resolver (T16). Spec: docs/specs/S09-jurisdiction.md.

Statewide design: offices come from the database, so any district or city works once its offices are added (S09). Maps a confirmed complaint's GPS or place name to a ward
office, or to the department's district fallback, for S10's create_ticket to finish routing.

Either of us can change this file. If you do, update docs/specs/S09-jurisdiction.md and tell the
other.
"""

import math
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz
from supabase import Client

from app.db import get_client
from app.schemas import OfficeLevel

GPS_TIE_BREAK_KM = 0.1  # S09 BEHAVIOR 1
NAME_MATCH_MIN_SCORE = 80.0  # S09 BEHAVIOR 2
NAME_TIE_BREAK_POINTS = 3.0  # S09 BEHAVIOR 2
EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class OfficeRef:
    id: int
    level: OfficeLevel
    office_name: str


@dataclass(frozen=True)
class JurisdictionMatch:
    office: OfficeRef
    confidence: float
    matched_via: Literal["gps", "name", "fallback"]


# S31: General Triage was renamed Human Evaluation. Until migration 002 (new desk) / 003 (cutover) has run on a database, the old desk still serves, so a
# server deployed before the migration never fails to file a complaint. Remove once every database has been cut over.
LEGACY_DEPARTMENTS = {"Human Evaluation": "General Triage"}


class JurisdictionError(RuntimeError):
    """No active office at all for a department -- a seed/spec misconfiguration (S09 ERRORS),
    not a per-request condition to swallow."""


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _fetch_offices(department: str, *, client: Client) -> list[dict]:
    return (
        client.table("offices")
        .select("id,level,name,aliases,centroid_lat,centroid_lng,office_name")
        .eq("department", department)
        .eq("active", True)
        .execute()
    ).data


def _match_by_gps(
    wards: list[dict], lat: float, lng: float, max_match_distance_km: float
) -> dict | None:
    candidates = [
        w for w in wards if w["centroid_lat"] is not None and w["centroid_lng"] is not None
    ]
    if not candidates:
        return None
    ranked = sorted(
        ((_haversine_km(lat, lng, w["centroid_lat"], w["centroid_lng"]), w) for w in candidates),
        key=lambda pair: pair[0],
    )
    best_distance, best_ward = ranked[0]
    if len(ranked) > 1 and (ranked[1][0] - best_distance) < GPS_TIE_BREAK_KM:
        return None  # tie -- no match (S09 BEHAVIOR 1)
    return best_ward if best_distance <= max_match_distance_km else None


def _match_by_name(wards: list[dict], place_name: str) -> tuple[float, dict] | None:
    scored = sorted(
        ((max(fuzz.WRatio(place_name, c) for c in (w["name"], *w["aliases"])), w) for w in wards),
        key=lambda pair: pair[0],
        reverse=True,
    )
    best_score, best_ward = scored[0]
    if best_score < NAME_MATCH_MIN_SCORE:
        return None
    if len(scored) > 1 and (best_score - scored[1][0]) <= NAME_TIE_BREAK_POINTS:
        return None  # tie -- no match (S09 BEHAVIOR 2)
    return best_score, best_ward


def _office_ref(row: dict) -> OfficeRef:
    return OfficeRef(id=row["id"], level=OfficeLevel(row["level"]), office_name=row["office_name"])


def resolve_office(
    department: str,
    lat: float | None,
    lng: float | None,
    place_name: str | None,
    max_match_distance_km: float,
    *,
    client: Client | None = None,
) -> JurisdictionMatch:
    """S09 BEHAVIOR: GPS first, then fuzzy name match, then the department's district fallback.
    Confidence: gps -> 1.0, name -> score/100, fallback -> 0.0."""
    client = client or get_client()
    offices = _fetch_offices(department, client=client)
    if not any(o["level"] == "district" for o in offices) and department in LEGACY_DEPARTMENTS:
        offices = _fetch_offices(LEGACY_DEPARTMENTS[department], client=client)
    wards = [o for o in offices if o["level"] == "ward"]
    districts = [o for o in offices if o["level"] == "district"]
    if not districts:
        raise JurisdictionError(f"no active district office for department {department!r}")
    fallback = districts[0]

    if lat is not None and lng is not None and wards:
        matched = _match_by_gps(wards, lat, lng, max_match_distance_km)
        if matched is not None:
            return JurisdictionMatch(_office_ref(matched), 1.0, "gps")

    if place_name and wards:
        result = _match_by_name(wards, place_name)
        if result is not None:
            score, matched = result
            return JurisdictionMatch(_office_ref(matched), score / 100, "name")

    return JurisdictionMatch(_office_ref(fallback), 0.0, "fallback")
