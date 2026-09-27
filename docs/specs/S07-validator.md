# S07 — Validator + Confirmation
Implements: T15 (`backend/app/validator.py`) · Used by: T18 (S04 §2 step 7) · Depends on: S03
service spec format (field type rules), S05 Turn Engine (`TurnResult` shape), S01 API contract
(`summary`, confirmation semantics) · Version: v1 · Status: Draft

## PURPOSE
The backend never trusts the Turn Engine's output (PROJECT.md §4, S01 §2 principle 2). This module
is where that trust boundary actually gets enforced: every field value S05 proposed is checked
against its spec type rule (S03 FIELDS table) before it can be stored or shown, and this is also
where the citizen-facing decision — ask another question, show a confirmation summary, or move on
to ticket creation — actually gets made (S04 §2 step 7, previously `[DECIDE]`).

## SCOPE
`backend/app/validator.py` (T15): merging and validating field values, completeness checking
(including the `location` field's GPS-vs-place-name duality), building the confirmation `summary`,
and picking the next `ask_for` question. Pure function, no I/O: no database, no LLM calls, no
jurisdiction resolution, no ticket creation. Does not decide the S01 `action` directly — see
DECISIONS D-S07-5 for why it has its own smaller vocabulary instead.

## INPUT
`apply()`'s parameters — this spec owns the signature named provisionally in S04 §3:

| Param | Type | Source | Notes |
|---|---|---|---|
| `specs` | `dict[str, ServiceSpec]` | `app.state.specs` (S03) | Same full set S05 receives — needed for the out-of-scope reply even when no service is identified yet |
| `session` | `SessionSnapshot` | T18, from `app.session.Session` | This module's own minimal view (service_id, collected_fields, awaiting_confirmation, lat, lng) — decoupled from `app.session.Session` the same way S05's `SessionState` is decoupled from it (D-S07-6) |
| `turn_result` | `turn_engine.TurnResult` | S05's `run_turn()` output | Untrusted: `service_id`, `fields`, `confirmed` |
| `lat`, `lng` | `float \| None` | S04 §2 step 1 (this turn's request) | THIS turn's GPS, if sent — distinct from `session.lat`/`session.lng`, which is whatever GPS a *previous* turn already stored (S02) |

`SessionSnapshot` (`service_id: str | None`, `collected_fields: dict[str, Any]`,
`awaiting_confirmation: bool`, `lat: float | None`, `lng: float | None`) — T18 builds it from
`app.session.Session` (four field copies plus renaming none), the same trivial-adapter pattern
already used for `turn_engine.SessionState`.

## OUTPUT
`ValidationResult`: `service_id: str | None`, `collected_fields: dict[str, Any]`,
`awaiting_confirmation: bool`, `action: ValidatedAction`, `ask_for: str | None`,
`reply_text: str | None`, `summary: dict[str, Any] | None`.

`ValidatedAction` (new enum, **not** S01's `Action` — see D-S07-5): `ask` · `confirm` ·
`out_of_scope` · `ready_to_submit`. `ready_to_submit` is never sent to the citizen: it tells T18
"all required fields validated and the citizen just confirmed — call S10 next" (S04 §2 step 7a).
`reply_text` is `None` exactly on `ready_to_submit` (T18 builds the real `submitted` reply itself,
once it has a `complaint_id` from S10 — this module never has one).

`collected_fields`/`awaiting_confirmation`/`service_id` in the result are what T18 puts into the
next `SessionUpdate` (S06) — this module computes them, T18 just carries them over.

## BEHAVIOR

### 1. Out-of-scope turns never touch session state
If `turn_result.service_id` is `None`, this turn is treated as not matching any loaded service —
**regardless of whether a service was already active** (D-S07-2). Result: `action=out_of_scope`,
`reply_text` = that service's `out_of_scope.reply.hi` (whichever spec `session.service_id` still
names, or — if no service was ever identified — the only loaded spec in M1; S03 OPEN / G-S05-3
already flag this as moot until a second service exists). `service_id`, `collected_fields`, and
`awaiting_confirmation` are all returned **unchanged from `session`** — a citizen mid-flow who sends
one unrelated message can pick up exactly where they left off on their next message, rather than
losing progress. Merging/validation (§2–4 below) is skipped entirely for this turn.

### 2. Merge and validate fields
Only reached when `turn_result.service_id` is not `None`. `spec = specs[turn_result.service_id]`
(safe by S05's own structural guarantee — D-S07 RULES §1). Starting from `session.collected_fields`,
for each `(name, raw_value)` in `turn_result.fields`:
- `name` not in `spec.fields` → dropped (S03 TURN RULES #4).
- `name` known, but `raw_value` fails its type rule (§3 below) → dropped, **the field's existing
  value (if any) is left exactly as it was** — an invalid proposed update never erases a
  previously-valid one (D-S07-4).
- Otherwise → the validated value replaces whatever was there for that field name.

### 3. Per-type validation rules (S03 FIELDS table)
| Type | Rule |
|---|---|
| `enum` | `raw_value` must equal one `values[].value` exactly (case-sensitive, already `snake_case` by S03) |
| `integer` | Coerced via `int(raw_value)` if it's an `int` or a numeric `str` (booleans explicitly rejected — `bool` is an `int` subclass in Python); must land in `[min, max]` |
| `string` | Must be a `str`; trimmed; kept if `1 <= len <= max_length` after trimming |
| `location` | Must be a `str` (the place-name form only — GPS never arrives through `fields`, S03); trimmed; kept if `accepts.place_name.min_length <= len <= accepts.place_name.max_length` |

### 4. `location` is satisfied by GPS *or* a place name
A required `location` field counts as satisfied if **either**:
- GPS was given — this turn (`lat`/`lng` both not `None`) **or** a previous turn (`session.lat`/
  `session.lng` both not `None`, S02: "last location sent" persists across turns, D-S07-3); **or**
- a validated place-name string is present in `collected_fields` for that field's `name` (§2–3).

GPS takes precedence for display (§5) and is what S09/S10 will actually route on later — this
module only decides "satisfied or not," never which one jurisdiction resolution should prefer.

### 5. Completeness → `ask`, `confirm`, or `ready_to_submit`
- **Any required field unsatisfied** (§4 for `location`, "has a validated value" for everything
  else) → `action=ask`. Pick the **first** such field in the spec's own `fields` order (S03 TURN
  RULES #1: one per turn). `ask_for` = that field's `ask_for` (locations already default this to
  their own `name` per `service_spec.py`'s `LocationField`). `reply_text` = that field's
  `question.hi`. `awaiting_confirmation=False`.
- **All required fields satisfied** — build `summary` (§6) from every *satisfied* field, required
  or optional:
  - `turn_result.confirmed` is `True` (only possible if `session.awaiting_confirmation` was already
    `True` — S05 D-S05-3 already guarantees this) → `action=ready_to_submit`, `awaiting_confirmation
    =False`, `reply_text=None` (T18 builds the real one after S10 returns a ticket).
  - Otherwise (first time reaching completeness, or a correction was just made) → `action=confirm`,
    `awaiting_confirmation=True`, `reply_text=CONFIRM_PROMPT_HI` (module constant, **PROPOSED** —
    see G-S07-1, no canonical confirmation-prompt text exists anywhere in the repo today).

### 6. Building `summary` (S01 §4.2/§4.4 note)
Iterate `spec.fields` in order; include a key only for fields that are satisfied per §4/§2-3.
Display value per type, chosen for what a citizen reviewing their own complaint can actually read
(not the raw stored value):
- `enum` → the matching value's `.hi` label (not the raw `snake_case` id).
- `integer` / `string` → the raw stored value, as-is.
- `location` → `GPS_LOCATION_LABEL_HI` (module constant, **PROPOSED**, G-S07-2) if satisfied via GPS;
  otherwise the stored place-name string.

## RULES
1. `turn_result.service_id` is trusted to already be `None` or a key of `specs` — S05's own
   structural validation (S05 §5.2) guarantees this; S07 does not re-check it.
2. This module never calls the database, the LLM, or jurisdiction resolution, and never decides
   `reply_text` for the `submitted` action — that needs a `complaint_id` only S10 can produce.
3. An invalid proposed field value is dropped silently; it is never surfaced as `action=error` (S03
   TURN RULES #4) — from the citizen's point of view it just means the field stays (or remains)
   unanswered, prompting the same or a re-phrased `ask`.
4. All citizen-facing copy this module produces is `.hi` only (D-S07-1) — there is no runtime
   language-selection feature; `.en` fields in specs are for developer/dashboard readability.

## ERRORS
There is no failure mode analogous to S05's provider outage — `apply()` is a pure function over
already-in-memory data (spec, session snapshot, `TurnResult`). A malformed `ServiceSpec` would have
already failed at startup (S03 loader); a malformed `TurnResult` would have already failed S05's own
structural validation. Nothing here raises under normal operation.

## OUT OF SCOPE
- Which office/ward a `location` value resolves to, or the `routing_confidence` score (S09/S10).
- Creating the `tickets` row, or building the final `submitted` `reply_text`/`ticket` object (S10,
  then T18).
- Choosing between two loaded services' `out_of_scope.reply` when more than one exists (S03 OPEN,
  moot in M1 — one spec).
- Any UI/UX design of the confirmation flow beyond the text this module returns.

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S07-1 | All generated reply text is `.hi` only | Matches PROJECT.md's "Hindi-first" pilot and S01's own examples (all Hindi); no language-detection/selection feature exists anywhere in the system to justify picking `.en` at runtime |
| D-S07-2 | An out-of-scope turn never mutates `service_id`/`collected_fields`/`awaiting_confirmation` | S04 §2 step 7 only says "not matching any loaded service → `out_of_scope`" — it doesn't say the citizen's in-progress complaint should be thrown away over one unrelated aside. Minimal-surprise choice; flagged as G-S07-3 for Lead to confirm or override, since it's citizen-facing behavior beyond what's explicitly written |
| D-S07-3 | Once GPS is given, `location` stays satisfied for the rest of the session, not just the turn it arrived on | Matches how every other required field already behaves (given once, stays given); S02's `sessions.lat/lng` already persists it as "last location sent" for exactly this reason |
| D-S07-4 | An invalid proposed value never erases an existing valid one for the same field | "Dropped, field stays missing" (S03 TURN RULES #4) generalizes most sensibly to "stays whatever it already was" — a single bad LLM extraction on turn 5 shouldn't undo a good one from turn 2 |
| D-S07-5 | A new `ValidatedAction` enum (`ask`/`confirm`/`out_of_scope`/`ready_to_submit`), not S01's `Action` | `ready_to_submit` is an internal signal for T18 to call S10 next — it is never a citizen-facing value, so reusing S01's `Action` (which has no such state) would be a type lie |
| D-S07-6 | `SessionSnapshot` is this module's own minimal dataclass, not `app.session.Session` | Same decoupling S05 already uses for its own `SessionState` — T18 is the only place that needs to know both shapes exist, and the adapter is three-to-four trivial field copies |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S07-1 | No canonical Hindi confirmation-prompt text exists anywhere in the repo — `CONFIRM_PROMPT_HI` is a PROPOSED placeholder (same convention as `water_supply.yaml`'s PROPOSED enum values), needing Lead/Dev sign-off | Before T15 implementation ships to citizens |
| G-S07-2 | No canonical "GPS location shared" display label for the confirmation summary either — `GPS_LOCATION_LABEL_HI` is likewise PROPOSED | Same as G-S07-1 |
| G-S07-3 | D-S07-2 (out-of-scope preserves session state instead of wiping it) is a judgment call filling a real gap in S04's wording, not something explicitly decided anywhere yet — flag for Lead to confirm before T15 ships, since it changes citizen-visible behavior | Before T15 implementation ships to citizens |
| G-S07-4 | Summary display for `integer`/`string` fields is the bare value with no unit or phrasing (e.g. `duration_days` shows as `3`, not "3 दिन से") — flag whether that reads well enough to citizens as-is, or whether per-field display phrasing belongs in S03's spec format instead of being invented here | Before T31 integration/demo review |

## ACCEPTANCE
| Item | Covered by |
|---|---|
| Scenario 1/2 (S01 §10.2): only `location` missing → `ask`, `ask_for="location"` | §5 "any required field unsatisfied" branch |
| Scenario 3: issue + place given together → `confirm` directly, no intermediate `ask` | §5 "all required fields satisfied" branch reached in one `apply()` call |
| Scenario 4: a correction at confirmation → `confirm` again with the corrected value in `summary`, not `ready_to_submit` | S05 already returns `confirmed=False` for a correction; §5's `else` branch |
| Scenario 6: an unrelated message → `out_of_scope`, no service invented, no fields touched | §1 |
| Scenario 7 (GPS path): GPS given, no place name → `location` still counts as satisfied | §4 |
| An LLM-proposed value outside the spec's allowed values is dropped and the field stays as it was (not blanked, not `action=error`) | §2, D-S07-4, RULES §3 |
| `session.awaiting_confirmation=False` and all required fields already satisfied from a single-message complaint → `confirm`, never `ready_to_submit` (S05's `confirmed` forcing already guarantees `turn_result.confirmed` can't be `True` here) | §5, relies on S05 D-S05-3 |
