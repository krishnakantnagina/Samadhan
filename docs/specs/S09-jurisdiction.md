# S09 — Jurisdiction (Pilot Data + Resolver)
Implements: T05 (data), T16 (resolver) · Used by: S10 (`create_ticket`) · Depends on: S02, S03, `specs/water_supply.yaml`, `docs/research/T05-research.md` · Version: v1 · Status: Draft

## PURPOSE
One resolver, one pilot dataset: map a confirmed water-supply complaint's GPS or place name to a Bhopal office, or to the district fallback, so S10 can finish creating the ticket.

## SCOPE
Bhopal, `water_supply` only. 5 pilot wards + 1 district fallback office (T05). No other city, service, or zone-level routing (T05 research found no verified zone map).

## INPUT
`department` (str, from the service spec), `lat`/`lng` (float, together, or both `None`), `place_name` (str or `None`) — the validated `location` field's two accepted forms (S03).

## BEHAVIOR
1. **GPS present:** distance to every active `ward`-level office's centroid for `department`. Nearest wins if within `routing.max_match_distance_km` (5, from `specs/water_supply.yaml`, already PROPOSED there — not re-decided here). Two+ wards within 0.1 km of each other → tie → no match.
2. **No GPS match (or none given):** fuzzy match `place_name` against each ward's `name` + `aliases` for `department` (`rapidfuzz.fuzz.WRatio`). Best score ≥ 80 wins; top two scores within 3 points of each other → tie → no match. **[DECIDE]** 80 / gap-of-3: no prior value existed anywhere in the repo; picked as a standard `rapidfuzz` cutoff, not sourced.
3. **No match either way (or a tie):** fallback = the department's one active `district` office.
4. **Confidence:** GPS match → `1.0`. Name match → `score / 100`. Fallback → `0.0`.

## OUTPUT
`JurisdictionMatch`: `office` (`id`, `level`, `office_name`), `confidence` (0–1), `matched_via` (`gps` \| `name` \| `fallback`).

## CONTRACT (S10 interface)
Module `app.jurisdiction` (**[DECIDE]**, matches S04 §3's naming style) — function `resolve_office(department, lat, lng, place_name) -> JurisdictionMatch`. Called once per confirmed ticket by S10's `create_ticket` (S04 §2 step 7a). S10 sets `ticket.status = needs_review` when `confidence < routing.min_confidence` or `matched_via == "fallback"`; else `new`.

## PILOT DATA (T05)
- **Org:** Bhopal Municipal Corporation (BMC) — VERIFIED, bhopal.nic.in. PHED runs ~60% of bulk supply, but M1 routes every `water_supply` complaint to BMC regardless (T05 research §7). `department` stays `Jal Vibhag` (matches `specs/water_supply.yaml`; **DEMO** — not confirmed as BMC's own term, kept for consistency with existing code).
- **5 wards** (all **DEMO** — 2024 delimitation unverified, ward count itself disputed 85 vs 86): `code` = ward number, `name` = Hindi ward name, `office_name` = `"Ward <name> Office"` (**DEMO**, constructed — not a found value). `centroid_lat/lng`: **NOT FOUND** for every ward → `NULL`.

| code | name (hi) |
|---|---|
| 1 | महात्मा गांधी |
| 24 | रानी कमलापति |
| 52 | मिसरोद |
| 60 | गोविंदपुरा |
| 80 | सर्वधर्म कोलार |

- **Fallback** (district, 1 row): `office_name` = "BMC Head Office", `code` = `BMC-HQ` (**DEMO**, assigned, not sourced), `centroid` `NULL`. Contact — **VERIFIED**: Harshwardhan Complex, Mata Mandir, Bhopal 462001.
- `officer_name`: **NOT FOUND** for all 6 rows (roles only, never names, per rule — none found either) → `NULL`.

## RULES
- Never invent ward names, codes, coordinates, offices, or people; `DEMO`/`NULL` instead.
- GPS-based ward matching is inert for M1 (all centroids `NULL`) until real centroids exist — every GPS-only turn falls through to name match, then fallback.
- `offices.department` must equal `specs/water_supply.yaml`'s `department` (S03 rule).

## ERRORS
- No active office at all for a department → misconfiguration (seed/spec mismatch); a startup/data invariant, not a per-request error for S10 to catch silently.
- A GPS or name tie is "no match" per BEHAVIOR, not an error.

## DEPENDENCIES
S02 `offices` table; S03 / `specs/water_supply.yaml` `routing` block; `rapidfuzz` — **not yet in `backend/pyproject.toml`**, add when T16 is built (not part of T05/T06); `docs/research/T05-research.md`.

## OUT OF SCOPE
Zone-level routing, any service besides `water_supply`, any city besides Bhopal, real officer names, office-load balancing.

## ACCEPTANCE
**T05:** 5 ward rows + 1 district row in `offices` for `department = Jal Vibhag`; `unique(department, level, code)` holds; exactly one active `district` row; every `DEMO` value labeled as such in `docs/plans/T05-plan.md`.
**T16:** GPS within 5 km of a ward centroid → that ward (once centroids are non-null); no GPS/name match or a tie → fallback + `needs_review`; name fuzzy match ≥ 80 on `name` or an alias → that ward; two wards scoring within 3 points of each other → fallback, not the higher one.
