# Plan: T16 — Jurisdiction resolver

Ticket: `docs/TICKETS.md` T16 (owner Dev, depends on T05/T06 — both `[x]`, done when "Correct
ward"). Spec: `docs/specs/S09-jurisdiction.md` (already written; this plan resolves its two
`[DECIDE]` items rather than drafting a new spec).

**Scope: T16 only.** This plan builds `backend/app/jurisdiction.py`. It does not touch ticket
creation (S10/T17), does not touch `app/validator.py`, `app/session.py`, or `main.py`/`routes.py`.

**Decisions this plan resolves (S09's own `[DECIDE]` items):**
- Module `app.jurisdiction`, function `resolve_office(department, lat, lng, place_name,
  max_match_distance_km, *, client=None) -> JurisdictionMatch` — matches S04 §3's naming style, as
  S09 itself suggested. `max_match_distance_km` is a parameter, not loaded from the spec internally
  — S09 BEHAVIOR §1 explicitly treats it as sourced from the caller (S10, which has the
  `ServiceSpec.routing` block); `jurisdiction.py` stays decoupled from `app.service_spec` entirely.

**New implementation decisions this plan makes** (S09 stays at the behavior level):
- `rapidfuzz` added to `backend/pyproject.toml` (S09 DEPENDENCIES already flags this as needed, not
  yet present) — `fuzz.WRatio(a, b)` for the 0–100 fuzzy score S09's BEHAVIOR §2 specifies.
- Haversine great-circle distance for the GPS branch (`lat`/`lng` are WGS84 decimal degrees, S01 §3)
  — no new dependency, a ~10-line formula.
- `JurisdictionError(RuntimeError)` for "no active district fallback office for this department" —
  S09 ERRORS calls this a startup/data invariant, not a per-request error to swallow, so it's raised
  uncaught (same posture S06 takes on DB errors: propagate to the FastAPI catch-all, not a special
  citizen-facing path).
- Same injectable `client: Client | None = None` seam as T14/T12 (`providers`/`client`), so tests
  supply a small fake and make zero network calls.
- Reuses `app.schemas.OfficeLevel` for `OfficeRef.level` rather than inventing a new enum — S01
  already defines the canonical set (`ward`/`zone`/`municipal_corp`/`gram_panchayat`/`block`/
  `district`), and `service_spec.py`'s `Routing.fallback_level` already reuses it too.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `backend/app/jurisdiction.py` | Create | `OfficeRef`, `JurisdictionMatch`, `JurisdictionError`, `resolve_office()` — the S09 deliverable |
| `backend/tests/test_jurisdiction.py` | Create | A minimal fake `offices` client + tests for every BEHAVIOR branch and tie-break |
| `backend/pyproject.toml` | Edit | Add `rapidfuzz>=3.0` |
| `README.md` | Edit | Attribution: rapidfuzz |
| `docs/TICKETS.md` | Edit (last step) | Tick T16 `[x]` |

Not touched: `backend/app/main.py`, `backend/app/routes.py`, `backend/app/validator.py`,
`backend/app/session.py`, `backend/app/service_spec.py`, `backend/mock/*`,
`backend/tests/contract/*` — S10/T17 calls `resolve_office` from `create_ticket` later.

## 2. Steps, in order

**S1 — `backend/pyproject.toml`.** Add `"rapidfuzz>=3.0"` to `dependencies`, `uv sync`.

**S2 — `backend/app/jurisdiction.py`: types and constants.**
```python
GPS_TIE_BREAK_KM = 0.1          # S09 BEHAVIOR 1
NAME_MATCH_MIN_SCORE = 80.0     # S09 BEHAVIOR 2, [DECIDE] already made in S09 itself
NAME_TIE_BREAK_POINTS = 3.0     # S09 BEHAVIOR 2
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


class JurisdictionError(RuntimeError):
    """No active office at all for a department -- seed/spec misconfiguration (S09 ERRORS)."""
```

**S3 — Haversine distance.**
```python
def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
```

**S4 — Fetch offices.**
```python
def _fetch_offices(department: str, *, client: Client) -> list[dict]:
    return (
        client.table("offices")
        .select("id,level,name,aliases,centroid_lat,centroid_lng,office_name")
        .eq("department", department)
        .eq("active", True)
        .execute()
    ).data
```
One query, both wards and the district fallback come back together; `resolve_office` partitions by
`level` afterward. (Real Supabase: plain `.select().eq().eq().execute()` always returns an
`APIResponse` with `.data` as a list — no `maybe_single()` quirk to handle here, unlike S06.)

**S5 — GPS matching.**
```python
def _match_by_gps(wards, lat, lng, max_match_distance_km) -> dict | None:
    candidates = [w for w in wards if w["centroid_lat"] is not None and w["centroid_lng"] is not None]
    if not candidates:
        return None
    ranked = sorted(
        (_haversine_km(lat, lng, w["centroid_lat"], w["centroid_lng"]), w) for w in candidates
    )
    best_distance, best_ward = ranked[0]
    if len(ranked) > 1 and (ranked[1][0] - best_distance) < GPS_TIE_BREAK_KM:
        return None  # tie
    return best_ward if best_distance <= max_match_distance_km else None
```

**S6 — Name matching.**
```python
def _match_by_name(wards, place_name) -> tuple[float, dict] | None:
    scored = [
        (max(fuzz.WRatio(place_name, c) for c in (w["name"], *w["aliases"])), w) for w in wards
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best_ward = scored[0]
    if best_score < NAME_MATCH_MIN_SCORE:
        return None
    if len(scored) > 1 and (best_score - scored[1][0]) <= NAME_TIE_BREAK_POINTS:
        return None  # tie
    return best_score, best_ward
```

**S7 — `resolve_office`.**
```python
def resolve_office(
    department: str,
    lat: float | None,
    lng: float | None,
    place_name: str | None,
    max_match_distance_km: float,
    *,
    client: Client | None = None,
) -> JurisdictionMatch:
    client = client or get_client()
    offices = _fetch_offices(department, client=client)
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


def _office_ref(row: dict) -> OfficeRef:
    return OfficeRef(id=row["id"], level=OfficeLevel(row["level"]), office_name=row["office_name"])
```
GPS is tried first whenever both are given (S09 BEHAVIOR order 1→2→3); a place name is never even
looked at if GPS already resolved.

**S8 — `backend/tests/test_jurisdiction.py`: minimal fake.**
Much simpler than T14's `FakeSupabaseClient` — this module issues exactly one query shape
(`.select().eq().eq().execute()`, no `maybe_single`/`insert`/`update`/`order`/`limit`). A small
`FakeOfficesClient(rows)` / `_OfficesQuery` pair, self-contained in this test file (not shared with
`test_session.py`'s fake, matching how every ticket so far keeps its own test double).

**S9 — Tests** (S09 ACCEPTANCE + BEHAVIOR, each with hand-built office rows):
- `test_gps_within_range_matches_nearest_ward` — two wards with distinct centroids, citizen's point
  close to one → `matched_via="gps"`, `confidence=1.0`, correct office.
- `test_gps_tie_falls_through` — two wards given the **same** centroid (distance gap = 0, forces a
  deterministic tie regardless of the haversine formula's precision) → GPS match rejected; falls to
  fallback when no `place_name` is given.
- `test_gps_too_far_falls_through` — nearest ward's distance exceeds `max_match_distance_km` →
  fallback.
- `test_no_ward_centroids_falls_through_to_name` — wards exist but `centroid_lat/lng` are `NULL`
  (today's actual seed data reality per T05) and GPS is given → falls straight to name matching.
- `test_name_match_above_threshold` — `place_name` exactly equals a ward's alias → `matched_via=
  "name"`, `confidence >= 0.8`.
- `test_name_no_match_falls_back` — an unrelated `place_name` → fallback, `confidence=0.0`.
- `test_name_tie_falls_back` — two wards given the **same** alias text (forces an identical score,
  a deterministic 0-point gap) → fallback, not either ward.
- `test_gps_takes_precedence_over_place_name` — both a valid GPS match and a valid place name given
  → `matched_via="gps"`.
- `test_no_gps_no_place_name_goes_straight_to_fallback` — neither given → fallback, `confidence=0.0`.
- `test_no_active_district_raises` — no `district`-level row in the fake data → `JurisdictionError`.

**S10 — `README.md` Attribution.** Add `rapidfuzz` to the Backend bullet list.

**S11 — Run the suite and lint.**
`cd backend; uv run pytest` (new tests green, all existing ones unaffected) and
`uv run ruff check . && uv run ruff format --check .`.

**S12 — Tick it off.** `docs/TICKETS.md`: T16 `[x]`, once S11 is green.

## 3. Acceptance coverage

| S09 acceptance item (T16 half) | Covered by |
|---|---|
| GPS within `max_match_distance_km` of a ward centroid → that ward (once centroids are non-null) | S9 `test_gps_within_range_matches_nearest_ward` |
| No GPS/name match or a tie → fallback + (S10 will set) `needs_review` | S9 `test_gps_too_far_falls_through`, `test_name_no_match_falls_back` |
| Name fuzzy match ≥ 80 on `name` or an alias → that ward | S9 `test_name_match_above_threshold` |
| Two wards scoring within 3 points of each other → fallback, not the higher one | S9 `test_name_tie_falls_back` |

`needs_review`/`new` status assignment itself is S10's job (T17), not tested here — S09's CONTRACT
section already says so explicitly ("S10 sets `ticket.status`...").

## 4. New libraries
`rapidfuzz>=3.0` (S09 DEPENDENCIES already flagged this as needed for T16). `README.md` Attribution
updated (S10 step above).

## 5. How existing tests stay unaffected
`backend/app/jurisdiction.py` is new and self-contained; nothing in `backend/mock/*`,
`backend/tests/contract/*`, `backend/tests/spec/*`, or the T12/T14/T15 test files imports it.

## Verification
1. `cd backend; uv run pytest` — new tests green, all existing ones unaffected.
2. `cd backend; uv run ruff check . && uv run ruff format --check .` — clean.
3. Manual, optional (needs real `.env`, Supabase project already live): call `resolve_office(
   "Jal Vibhag", lat=None, lng=None, place_name="Misrod", max_match_distance_km=5)` against the
   real seeded `offices` table, confirm it resolves to the मिसरोद ward via its `Misrod` alias.

## Not doing in this turn
Not implementing `jurisdiction.py` itself until this plan is reviewed — same two-step pattern as
T12/T14/T15.
