"""GPS point -> district (audit: a citizen who shares their location was never asked a district, so the district stayed unknown and routing fell back).

Data: `specs/registry/district_geo.json`, built by `scripts/build_district_geo.py` from OpenStreetMap boundaries (OpenStreetMap contributors, ODbL) and the
district headquarters points. Method: the polygon that contains the point wins; a point in no polygon (a border rounding error, or a district whose boundary
OpenStreetMap does not have yet) goes to the nearest district centre if that is within `MAX_CENTRE_KM`, else no district. Never raises.

Either of us can change this file. If you do, update docs/specs/S39-district-desks.md.
"""

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

GEO_FILE = Path(__file__).resolve().parents[2] / "specs" / "registry" / "district_geo.json"
MAX_CENTRE_KM = 35.0
EARTH_RADIUS_KM = 6371.0


def _in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray casting: is the point inside this ring of [lng, lat] points?"""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _in_polygon(lng: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    """A polygon is [outer ring, hole, hole ...]."""
    return _in_ring(lng, lat, polygon[0]) and not any(_in_ring(lng, lat, hole) for hole in polygon[1:])


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@lru_cache(maxsize=4)
def load(path: str = str(GEO_FILE)) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))["districts"]
    except (OSError, ValueError, KeyError):
        return {}


def district_for(lat: float | None, lng: float | None, *, path: str | None = None) -> str | None:
    """The English district name (as in specs/registry/districts.yaml) for a GPS point in Madhya Pradesh, or None."""
    try:
        if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None
        districts = load(path) if path else load()
        for name, d in districts.items():
            min_lng, min_lat, max_lng, max_lat = d.get("bbox") or (-181, -91, 181, 91)
            if not (min_lng <= lng <= max_lng and min_lat <= lat <= max_lat):
                continue  # cheap rejection: most districts are nowhere near the point
            if any(_in_polygon(lng, lat, polygon) for polygon in d.get("polygons", [])):
                return name
        nearest = min(
            ((_haversine_km(lat, lng, d["centre"][0], d["centre"][1]), name) for name, d in districts.items() if d.get("centre")),
            default=None,
        )
        return nearest[1] if nearest and nearest[0] <= MAX_CENTRE_KM else None
    except Exception:  # noqa: BLE001 -- a broken data file must never stop a complaint
        return None
