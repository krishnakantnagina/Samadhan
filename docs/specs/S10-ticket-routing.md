# S10 — Ticket + Routing
Implements: T17 (`backend/app/ticketing.py`) · Used by: T18 (S04 §2 step 7a) · Depends on: S02 DB
schema (`tickets`), S07 Validator (`ValidationResult.collected_fields`), S09 Jurisdiction
(`resolve_office`), S01 API contract (`Ticket`/`Office`) · Version: v1 · Status: Draft

## PURPOSE
The last step of a confirmed complaint: resolve which office it belongs to (S09), decide whether
that resolution is confident enough to route directly or needs an officer's eyes first, write the
`tickets` row, and hand back the `Ticket` object S01 §4.4 promises the citizen (S04 §2 step 7a, only
reached once S07 returns `ready_to_submit`).

## SCOPE
`backend/app/ticketing.py` (T17): calling S09's `resolve_office`, deciding `new` vs `needs_review`,
building `summary_en`, and inserting the `tickets` row. Does not resolve jurisdiction itself (S09
owns that), does not decide whether a turn is ready to submit (S07 owns that — this module is only
ever called once that's already `true`), and does not touch `sessions`/`messages` (S06's job —
clearing the session after submission is T18's responsibility, per S06 RULES §3).

## INPUT
`create_ticket()`'s parameters — this spec owns the signature named provisionally in S04 §3:

| Param | Type | Source | Notes |
|---|---|---|---|
| `session_id` | `uuid.UUID` | T18 | Only the id is needed — `tickets.session_id` is a bare FK; every other session field is already folded into `validated_fields` by S07 |
| `spec` | `ServiceSpec` | `app.state.specs[validation_result.service_id]` | The confirmed service's spec — `department`, `routing`, and field definitions all come from here |
| `validated_fields` | `dict[str, Any]` | `ValidationResult.collected_fields` (S07) | Already type-checked; this module trusts it completely (RULES §1) |
| `lat`, `lng` | `float \| None` | This turn's request, same as S05/S07 | Passed straight through to S09; `None` if the location field was satisfied by a place name instead |
| `original_text` | `str` | T18 (not yet decided which message — see G-S10-1) | Stored verbatim in `tickets.original_text` (S02); this module never inspects or reshapes it |
| `audio_path` | `str \| None` | T18 / S12 | Stored verbatim in `tickets.audio_path` (S02), same passthrough posture S06 already takes |

`session_id`, not a `Session`/`SessionSnapshot` object (D-S10-4) — this module is decoupled from
`app.session`'s and `app.validator`'s own types the same way S07 is decoupled from `app.session`.

## OUTPUT
`schemas.Ticket` (S01 §4.4): `complaint_id`, `department`, `office` (`{name, level}`), `status`.
Raises uncaught on any failure — see ERRORS. There is no "ticket creation failed gracefully" path:
S04 §4 already classifies a ticket-creation failure (other than routing confidence, which is never a
failure) as `500 INTERNAL_ERROR`.

## BEHAVIOR

### 1. Find the location field
`spec.fields` is scanned for the one field with `type == "location"` (`water_supply.yaml` has
exactly one; S03 doesn't forbid more, but M1 never has more than one — see G-S10-2). Its `name` is
the key looked up in `validated_fields` for a place name, if any.

### 2. Resolve jurisdiction (S09)
```
match = jurisdiction.resolve_office(
    department=spec.department,
    lat=lat,
    lng=lng,
    place_name=validated_fields.get(location_field.name),
    max_match_distance_km=spec.routing.max_match_distance_km,
)
```

### 3. Decide `new` vs `needs_review`
`needs_review` if `match.confidence < spec.routing.min_confidence` **or** `match.matched_via ==
"fallback"` — else `new` (S09 CONTRACT already states this rule; written out literally here even
though a `fallback` match's confidence is always `0.0` and so already fails the first check on its
own — belt and suspenders, not two independent conditions in practice, D-S10-3).

### 4. Build `summary_en`
A single English string for officers (S02 `tickets.summary_en`), built from `validated_fields` and
`spec`'s `.en` labels — **not** from `original_text` (D-S10-2). For each field in `spec.fields`
order that's satisfied (same satisfaction check S07 already uses): `enum` → `label.en: value.en`;
`integer`/`string` → `label.en: <value>`; `location` → the place name if given, or the **numeric**
`lat, lng` coordinates if GPS-based (unlike S07's citizen-facing summary, which shows a generic "GPS
shared" label — officers reviewing this on the dashboard's map (T30) benefit from the actual
numbers). Joined with `"; "`.

### 5. Insert the `tickets` row
```
tickets.insert({
    session_id, service_id: spec.service, department: spec.department,
    office_id: match.office.id, status, fields: validated_fields,
    summary_en, original_text, audio_path, lat, lng,
    routing_confidence: match.confidence,
})
```
`complaint_id` is **never computed here** — it's a DB `GENERATED ALWAYS AS STORED` column (T03); the
insert's own response (`representation`, the `supabase-py` default) already returns it fully formed,
with no truncation above 9999 (D-S10-6).

### 6. Build the response
`schemas.Ticket(complaint_id=<from the inserted row>, department=spec.department, office=Office(
name=match.office.office_name, level=match.office.level), status=<new|needs_review>)`.

## RULES
1. `validated_fields` is trusted completely — every value in it already passed S07's type checks
   against `spec`. This module does no re-validation of field values, only field *presence* (to find
   the location field's value, if any).
2. This module never decides `action`, never touches `sessions`/`messages`, and never writes
   `routing_corrections` (that's dashboard/officer territory, S02 RULES §3).
3. `original_text`/`audio_path` are opaque passthrough strings — this module stores exactly what
   it's given, the same posture S06 already takes on `audio_path` (S06 SCOPE).
4. Any failure here — jurisdiction misconfiguration (S09's `JurisdictionError`) or a DB error —
   propagates uncaught. Only a low routing *confidence* is handled gracefully (as `needs_review`);
   an actual system fault is not silently downgraded to a citizen-facing state (S04 §4).

## ERRORS
| Situation | Result |
|---|---|
| No active district office for the department (S09 `JurisdictionError`) | Propagates uncaught → `500 INTERNAL_ERROR` (S04 §4) — a seed/spec misconfiguration, not a per-request condition |
| Low routing confidence, or a GPS/name tie in S09 | **Not an error** — `status = needs_review` (§3) |
| `tickets` insert fails (DB error) | Propagates uncaught → `500 INTERNAL_ERROR` |
| No `type: location` field found in `spec.fields` | Programming/spec error (every M1 service must have exactly one) — propagates uncaught, not a per-request condition |

## OUT OF SCOPE
- Jurisdiction matching logic itself (S09).
- Deciding *when* a turn is ready to submit (S07); this module is only ever called from that one
  branch.
- Clearing session state after submission, or building the citizen-facing `submitted` `reply_text`
  (both T18's job — this module only returns the `Ticket` object, T18 wraps it into a
  `MessageResponse`).
- Officer reassignment, `routing_corrections` (dashboard).

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S10-1 | `original_text`/`audio_path` are opaque passthrough parameters; this module never decides how they're sourced | Mirrors S06's existing posture on `audio_path` — keeps the question of "which citizen message counts as the original text" out of this module, since it's genuinely undecided anywhere yet (G-S10-1) |
| D-S10-2 | `summary_en` is generated from `validated_fields` + `spec`'s English labels, using real coordinates for a GPS-based location (not a placeholder label) | Distinct audience from S07's citizen-facing `summary`: officers view this on a dashboard with a map (T30), so exact numbers are more useful than a vague "GPS shared" string |
| D-S10-3 | `needs_review` iff `confidence < min_confidence` **or** `matched_via == "fallback"`, written as both checks even though they're practically redundant today | Matches S09 CONTRACT's own wording exactly, so a future change to fallback's confidence value (currently always `0.0`) doesn't silently change routing behavior |
| D-S10-4 | `create_ticket` takes `session_id: uuid.UUID`, not a `Session`/`SessionSnapshot` object | Nothing else about the session is needed once S07 has already merged everything relevant into `validated_fields` |
| D-S10-5 | DB errors and `JurisdictionError` propagate uncaught | Same posture as S06/S09: a system fault is a `500`, not a citizen-facing outcome — only routing *confidence* is a graceful, expected case |
| D-S10-6 | `complaint_id` is read back from the DB's generated column, never computed in Python | T03 already guarantees no truncation/collision (the `lpad`/sequence design); duplicating that logic here would be a second source of truth for no benefit |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S10-1 | Which citizen message becomes `original_text` is not decided anywhere in the repo yet — the last substantive complaint text (not a bare "yes"/"haan" confirmation), the very first message, or something else. T18 (not yet built) must decide and pass the right string in; this module only stores whatever it's handed | Before T18 implementation |
| G-S10-2 | `_find_location_field` assumes exactly one `type: location` field per spec (true today); S03 doesn't explicitly forbid more than one. Moot until a second, more complex service exists (mirrors S03/S05's existing single-service-instance simplifications) | Whenever a more complex service spec is added |

## ACCEPTANCE
| Item | Covered by |
|---|---|
| Scenario 7 (S01 §10.2): GPS in a pilot ward → `action = submitted`, `ticket.office.level = "ward"` | §2–3, §6, confidence `1.0` from a GPS match ≥ `min_confidence` |
| Scenario 8: unknown location → `ticket.office.level = "district"`, `ticket.status = "needs_review"` | §3, a `fallback` match from S09 |
| `complaint_id` matches `SMD-\d{4,}`, never truncated above 9999 | §5, D-S10-6 (T03's own generated-column guarantee) |
| `routing_confidence` stored as S09's `confidence` (0.00–1.00) | §5 |
| `tickets.office_id` is the FK S09 resolved, not a name string | §5, §6 |
