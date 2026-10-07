# S39 District desks and routing by district

Builds on S09 (jurisdiction) and S38 (migrations 005 and 006). The data and its sources are in `docs/DISTRICT_DESKS.md`; this is how the code uses it.

## Resolution order (`app/jurisdiction.resolve_office`)
1. **The citizen's district** is the one they typed (the intake notes), else the one found from a shared GPS point (`app/district_geo.py`), else unknown.
2. GPS match against ward offices, then a place-name match against ward offices, both **only among the wards of that district**. With the district unknown and a department that has offices in several districts, a place name is never
   matched (the same village name exists in many districts); GPS still is.
3. **That district's desk** for the department (`level = 'district'`): matched_via `district`, confidence 0.7, status **new**.
4. **The state desk** (`level = 'state'`) when the department has no desk in the citizen's district, or has no district desks at all: matched_via `state`, confidence 0.7, status **new**.
   With the district still unknown and district desks existing, this step is skipped, so the bot asks for the district first.
5. **The department's default desk** (the old behaviour): matched_via `fallback`, confidence 0, status **needs_review**.
6. A department with no office of any kind sends the complaint to the Human Evaluation desk for review (`ticketing.create_ticket`); only a missing Human Evaluation desk raises an error.

## Data
- `offices.district` (migration 005): English district name as in `specs/registry/districts.yaml`. One active district desk per (department, district).
- `offices.level = 'state'` (migration 007): a state-level desk; `OfficeLevel.STATE` in the API schema.
- `specs/registry/district_desks.yaml` decides, per department, district or state scope and the desk's designation; `backend/scripts/gen_district_desks.py` turns it into migration 007 and the table in
  `docs/DISTRICT_DESKS.md`. Edit the yaml, run the script, apply the migration (re-running is safe).
- `specs/registry/district_geo.json`: simplified boundaries of the 55 districts (about 2 km), built by `backend/scripts/build_district_geo.py` from OpenStreetMap data.

## Other fixes made while building it
- A GPS location shared in an earlier message now reaches the ticket (it was only used when sent in the confirming message itself).
- The ticket's `district` column and `location_precision` ("exact") are filled from GPS when the citizen typed no district.

## Tests
`tests/test_jurisdiction.py` (district rules), `tests/test_district_geo.py` (boundaries, 21 known places, state desks, GPS carried to the ticket), `tests/test_ticket_duplicates.py` (no office -> Human Evaluation).
Real conversations were run against a local database loaded with migrations 002 to 005 and 007: a Rajgarh road complaint -> "Zila Panchayat CEO Office, Rajgarh" (new); a Satna GPS complaint with no typed district ->
"District Education Officer, Satna" (new); a tourism complaint -> "Madhya Pradesh Tourism Board, Bhopal (state)" (new).

## Limits
Block, tehsil and municipal-ward offices are not modelled beyond the Bhopal demo wards. Boundaries are simplified. Designations are standard structure read from public directories, not confirmed by the departments.
