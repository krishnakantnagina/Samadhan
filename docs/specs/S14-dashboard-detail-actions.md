# S14 — Dashboard: Detail, Status, Reassign, Review Queue
Implements: T24 (`dashboard/src/dashboard/`) · Depends on: S13 (auth/list/client already built),
S02 DB schema (`tickets`, `offices`, `routing_corrections`) · Version: v1 · Status: Draft

## PURPOSE
Everything S13's list view deliberately left out: opening one ticket, changing its status,
reassigning it to a different office, and a dedicated queue for the tickets that need an officer's
attention first. This is the dashboard's only write path — S02 RULES §3 names exactly two columns
the dashboard may ever update (`tickets.status`, `tickets.office_id`) plus one table it may insert
into (`routing_corrections`); nothing here writes anything else.

## SCOPE
`dashboard/src/dashboard/tickets.py` (extended: detail fetch, office list, the two writes,
correction history) and `app.py` (extended: a selectable row on the existing list opens a detail
panel; a second tab is the review queue). T30 (map) is still a separate, later ticket — not here.

## DATA ACCESS (new reads/writes on top of S13)

| Function | Table(s) | Verb | Notes |
|---|---|---|---|
| `get_ticket_detail(complaint_id)` | `tickets` (+ `offices` embed) | SELECT | Unlike S13's list query, this *does* include `fields`, `original_text`, `lat`/`lng`, `audio_path` (S13 RULES §2 was a list-view rule, not a blanket one — a deliberately opened single ticket is exactly where this detail belongs, same distinction S01 draws between the citizen status endpoint and the full `Ticket` object) |
| `list_offices_for_department(department)` | `offices` | SELECT | `active = true`, ordered `level, code` — the reassign dropdown's options |
| `update_status(complaint_id, new_status)` | `tickets` | UPDATE | Only column touched: `status`. `updated_at` is the table's own trigger (`touch_updated_at`, T03) — this module never sets it |
| `reassign_ticket(ticket_id, from_office_id, to_office_id, reason)` | `tickets`, `routing_corrections` | UPDATE + INSERT | Two calls, not one transaction — see D-S14-2 |
| `list_routing_corrections(ticket_id)` | `routing_corrections` | SELECT | History for the detail panel; office *names* resolved in Python from a cached `offices` lookup, not a double PostgREST embed (D-S14-3) |

All six take the same `*, client: Client | None = None` shape as S13's `list_tickets` and every
backend module before it — consistent, testable against a fake client, no live DB in tests.

## BEHAVIOR

### 1. Opening a ticket
The "All Tickets" list (S13) gains row selection (`st.dataframe(..., on_select="rerun",
selection_mode="single-row")`, supported since Streamlit 1.35 — this project is on 1.64). Selecting
a row calls `get_ticket_detail` for that `complaint_id` and renders the detail panel below the
table. No separate search/lookup UI needed — the list is already filterable (S13).

### 2. Detail panel
Shows, in addition to everything S13's list row already had: the structured `fields` (as
label: value pairs, using the same field labels the citizen sees — no separate officer-facing label
set exists, and inventing one is out of scope), `original_text` verbatim, `lat`/`lng` if GPS-based,
`routing_confidence`, and — only if `audio_path` is not null — an audio player via a signed URL
(§4). Also lists this ticket's `routing_corrections` history, newest first, if any exist.

### 3. Status change
A selectbox of all four `ticket_status` values (S02), defaulted to the ticket's current status. A
"Save status" button calls `update_status`. No transition rules — S02 doesn't define any (e.g.
`resolved → new` is not forbidden anywhere), so none are invented here (PROJECT.md §9 rule 2).

### 4. Reassign
A selectbox of `list_offices_for_department(ticket.department)`, excluding the ticket's current
office, plus an optional free-text reason. A "Reassign" button:
1. Rejects `to_office_id == from_office_id` in the app itself, with a plain message — not just
   relying on the DB's own `CHECK (from_office_id <> to_office_id)` to surface as a raw error (S02
   ERRORS: "Reassign to same office → rejected").
2. Calls `reassign_ticket`, which updates `tickets.office_id` and inserts one `routing_corrections`
   row (S02 ACCEPTANCE: "Reassignment writes one `routing_corrections` row and changes
   `tickets.office_id`").
3. Invalidates the cached ticket list (`st.cache_data.clear()` on the S13 fetch) so the list and any
   open detail panel reflect the new office on the next render, not stale cached data for up to 30s.

### 5. Review queue
A second tab, "Review Queue": the same detail-capable table as "All Tickets", pre-filtered to
`status == "needs_review"`, no filter controls of its own (it's already fully scoped). Built from
the same cached fetch as "All Tickets" (S13 D-S13-3) — not a second query — filtered in Python.
Reviewing a ticket here is the same detail panel as §2; there is no separate "review" action beyond
changing its status and/or reassigning it, which is already everything §3/§4 provide.

## AUDIO PLAYBACK (only reached if a ticket has `audio_path`)

No seeded or real ticket has one yet (voice/T26 hasn't shipped), so this path is built to spec but
**not yet exercised against a real audio file** — flagged honestly, not claimed as verified (G-S14-1).

```python
client.storage.from_("audio").create_signed_url(path=audio_path, expires_in=300)
```
`expires_in` in seconds (G-T06-2 asked for a real value, not an assumed ceiling — `300`s, long
enough for an officer to listen without a link that lingers). `st.audio(signed_url)`.

## RULES
1. The dashboard writes exactly `tickets.status`, `tickets.office_id`, and inserts
   `routing_corrections` rows — nothing else, ever (S02 RULES §3, verbatim).
2. `reassign_ticket` rejects same-office reassignment in application code, before it reaches the DB
   (S02 ERRORS).
3. No new business rules on status transitions, review resolution, or reassignment eligibility — S02
   defines none, so none are invented (PROJECT.md §9 rule 2).
4. `updated_at` is never set by this module — it's `tickets`' own `BEFORE UPDATE` trigger (T03).
5. A ticket's `fields`/`original_text`/`lat`/`lng`/`audio_path` are fetched only by
   `get_ticket_detail` (one ticket, deliberately opened), never added back to the S13 list query.

## ERRORS
| Situation | Result |
|---|---|
| Reassign to the same office | Rejected in-app before any DB call, plain message (§4 step 1) |
| `update_status`/`reassign_ticket` DB call fails | `st.error`, same posture as S13's list-fetch failure — not a crash |
| `get_ticket_detail` finds no row (ticket removed between list render and click — race, unlikely at this scale) | `st.warning`, no detail panel |
| Signed URL creation fails (no `audio_path`, bad path, storage error) | `st.warning` on the audio section only — never blocks the rest of the detail panel |

## OUT OF SCOPE
- Map (T30 — own spec).
- Any transition/eligibility rules beyond what S02 already states.
- Real-time updates (S13's 30s cache + this ticket's manual `st.cache_data.clear()` on write is the
  whole freshness story — no websockets/polling).
- Bulk actions (reassign/status-change more than one ticket at once).

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S14-1 | Field labels shown in the detail panel reuse the citizen-facing `.en` labels from `specs/water_supply.yaml` fields, hardcoded here rather than loaded from the YAML | The dashboard is a separate `uv` project with no `app.service_spec` import available; `fields`' *keys* are already stable (S03: they're the API contract), and duplicating 4 label strings is far cheaper than a cross-project YAML loader for one hackathon ticket |
| D-S14-2 | `reassign_ticket`'s update + insert are two sequential calls, not one atomic transaction | No RPC-based transaction exists anywhere in this project yet (S10's own `create_ticket` is a single insert, not a multi-statement transaction either); introducing one now for a hackathon-scale, single-operator dashboard is disproportionate. A failure between the two calls is a real but narrow gap, noted not hidden (G-S14-2) |
| D-S14-3 | `routing_corrections`' office names are resolved via a small in-Python lookup dict (all offices, ~6 rows, already fetched for the reassign dropdown), not a double PostgREST embed | A double embed of the same target table (`from_office_id`/`to_office_id` both → `offices`) needs named FK-constraint hints PostgREST requires explicitly; `schema.sql` never named those constraints, so guessing Postgres's auto-generated names is more fragile than a six-row Python dict |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S14-1 | Audio playback is built but has never been exercised against a real `audio_path` (no ticket has one until T26 ships voice) | Before claiming this feature demoed live |
| G-S14-2 | `reassign_ticket`'s two-call, non-atomic write (D-S14-2): a failure between the `tickets` update and the `routing_corrections` insert leaves the office changed but no correction logged | Revisit only if it's ever observed in practice — noted, not fixed pre-emptively |

## ACCEPTANCE
| Item | Covered by |
|---|---|
| TICKETS.md "Saves to DB" | §3, §4 |
| Status change persists and is visible on next list refresh | §3, cache invalidation |
| Reassignment writes one `routing_corrections` row and changes `tickets.office_id` (S02 ACCEPTANCE, verbatim) | §4 steps 2–3 |
| Reassign to same office → rejected | §4 step 1, RULES §2 |
| Review queue shows only `needs_review` tickets, reuses the same detail/actions | §5 |
| No new column beyond `status`/`office_id`/`routing_corrections` is ever written | RULES §1 |
