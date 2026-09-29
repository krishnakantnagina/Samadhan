# S24 — Dashboard map (T30)
Implements: `dashboard/src/dashboard/{tickets.py,map_view.py,app.py}` · Depends on: S13, S14, S02 · Version: v1 · Status: Draft

## 1. Purpose
T30 "Dashboard map: pins show". Officers see where complaints are on a map of Bhopal, coloured by status, and can
open a ticket from it. `folium` and `streamlit-folium` are already dependencies (`dashboard/pyproject.toml`).

## 2. Data reality (checked live, 29 Sep 2026)
- Only tickets with a stored GPS (`tickets.lat`/`lng`) have an exact position: **2 of 20** today.
- All ward `offices.centroid_lat/lng` are `NULL` (S09: real centres NOT FOUND, never guess).
- **Decision (Lead, 29 Sep):** no invented coordinates. The map pins **exact GPS only**. S23 makes the citizen flow ask for
  GPS explicitly so future tickets carry it. Tickets without GPS are **counted and listed**, never faked onto the map.

## 3. Behaviour
1. New third tab **"Map"** next to "All Tickets" and "Review Queue".
2. Uses the **same filters** as All Tickets (status, department, office, search): shared state, not a copy.
3. Pins: `folium.CircleMarker`, colour by status (new = blue, in_progress = amber, resolved = green, needs_review = red),
   with a legend that names each status so colour is never the only cue, and the status text in every popup.
4. Popup/tooltip: complaint ID, status, issue (English label from `labels.py`), office, created time.
5. Map fits its bounds to the pins when there are 2+, centres on the single pin at zoom 15 when there is one, and shows the
   default Bhopal centre (23.2599, 77.4126) at zoom 11 when there are none.
6. Below the map: **"N ticket(s) have no GPS and are not on the map"** with an expander listing them (ID, status, the
   location text the citizen gave). Honest count, not hidden.
7. Selecting a ticket from a "Open ticket" picker under the map shows the existing detail panel (`_render_detail`).
   (Click-a-pin-to-open would need `streamlit-folium` round-trip state; if it works reliably it may replace the picker, but
   the picker is the guaranteed path.)
8. Empty states: no tickets → existing "No tickets yet"; tickets but none with GPS → info message + the list.
9. A map that fails to render must not break the other tabs (error shown inside the tab only).

## 4. Data access
New `tickets.list_map_points()` selects only what the map needs:
`complaint_id,status,department,summary_en,fields,lat,lng,created_at,offices(office_name)`. It is **not** `select("*")`
and never selects `original_text`, `audio_path` or `session_id`. `lat`/`lng` were excluded from the S13 *list* view on
purpose; the map is a separate view for authenticated officers, the same audience that already sees GPS in the detail
panel (S14). Cached 30 s like the list, cleared after any write (S14). Read-only: the map writes nothing (S02 RULES 3).

## 5. Out of scope
- Marker clustering, heatmaps, ward polygons (no boundary data exists).
- Approximate/DEMO ward points for non-GPS tickets (declined by the Lead).
- Editing a ticket's location.

## ACCEPTANCE
- [x] Map tab renders with pins for every ticket that has GPS (2 with today's data)
- [ ] Pin colour follows status; legend and popup show the status text
- [ ] Filters change the pins
- [x] "N without GPS" count and list are correct (18 today)
- [ ] Picking a ticket under the map opens its detail panel (needs a browser)
- [x] No-pins / no-tickets states handled; a map error does not break other tabs
- [x] Pure logic (split with/without GPS, colour, popup text, centre/zoom) unit-tested; `uv run pytest` and ruff pass in `dashboard/`
- [x] Nothing written to the DB; no columns selected beyond §4

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S24-1 | Exact GPS only, count the rest | Lead's decision; S09 forbids invented coordinates |
| D-S24-2 | Separate `list_map_points` query | Keeps S13's minimal list query untouched |
| D-S24-3 | Map logic in `map_view.py` with pure helpers | Unit-testable without Streamlit |
| D-S24-4 | Picker under the map is the guaranteed way to open a ticket | Pin-click state through `streamlit-folium` is not guaranteed across reruns |

## BUILD LOG (29 Sep 2026)
Verified: `dashboard` pytest 25 passed (10 new). The real app was run with Streamlit's `AppTest` (auth flag set, no
password typed) against the live Supabase data: no exceptions, tabs `All Tickets / Review Queue / Map`, caption
"2 ticket(s) on the map.", warning "18 ticket(s) have no GPS and are not on the map.".
**Not verified:** the tiles/markers drawn in a real browser (needs the login and a person looking), the filter
interaction (filters are shared through the same `filtered` frame; untested in a browser), and the "Open ticket"
picker's detail panel. `use_container_width` deprecation warnings come from the existing table code too.
