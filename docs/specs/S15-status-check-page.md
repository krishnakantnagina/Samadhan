# S15 — Status-Check Page
Implements: T22 (`frontend/status.html`, `frontend/status.js`) · Used by: citizen status-check flow
(PROJECT.md §2 scope row "status page") · Depends on: S01 API contract §5 (`GET
/api/v1/status/{complaint_id}`), S11 Status lookup (backend side, already built) · Version: v1 ·
Status: Draft

## PURPOSE
Lets a citizen who already has a `SMD-xxxx` complaint ID check its current status without going
through the chatbot again. Purely a read: calls the existing `GET /api/v1/status/{complaint_id}`
endpoint (S01 §5, built at T19/S11) and displays the four returned fields. No new backend work —
S11's header already named this page as its consumer.

## SCOPE
A second static page, `frontend/status.html` + `frontend/status.js`, added next to the existing
chat page (`index.html` + `app.js`). Reuses `frontend/style.css`. No routing/build step, matching
the rest of `frontend/` (T21). Does not touch the chatbot flow, does not create or modify tickets,
does not call `POST /api/v1/message`.

## BEHAVIOR
1. A form with one text input (placeholder `SMD-0042`) and a submit button.
2. On submit: trim the input, validate it client-side against the same pattern the backend uses
   (`^SMD-\d{4,}$`, S01 `COMPLAINT_ID_PATTERN`). Invalid or empty → inline error, **no** network
   call.
3. Valid format → `GET {API_BASE}/api/v1/status/{complaint_id}` (no body, no `session_id`; S01 §3:
   "Auth: None" for this endpoint).
4. `200` → render a result card: complaint ID, status (mapped to a Hindi label, see DECISIONS),
   department, and `updated_at` (formatted for a citizen, not raw ISO 8601).
5. Non-2xx → render a single error message. S01 §7: every non-2xx body includes a citizen-safe
   `reply_text` field — show it directly if present, otherwise fall back to a generic Hindi retry
   message, the same pattern `app.js`'s `sendToApi` already uses for `POST /message`.
6. One-shot lookup per submit. No auto-refresh, no polling (see D-S15-4).

## RULES
1. Client validates the complaint ID format before calling the API — mirrors S11 RULES §1's
   "format check before touching anything downstream," applied here to avoid a needless request
   instead of a needless DB call.
2. The page makes exactly one kind of call: `GET /api/v1/status/{complaint_id}`. It never calls
   `POST /api/v1/message` and never reads/writes the DB directly (S01 §1: the website only talks to
   the core API).
3. No fields beyond the four the endpoint returns are shown or stored — nothing here should imply
   more citizen data is available than S01 §5 actually returns (no transcript, audio, location,
   contact details, or collected fields exist to leak, since the endpoint never returns them).
4. Reuses `frontend/style.css`; any new classes follow the existing naming (`card`, `card-title`,
   `badge`, …) already established in `app.js`'s `appendTicketCard`/`appendSummaryCard`.

## ERRORS (client-side handling)
| Situation | UI behavior |
|---|---|
| Empty input | Inline validation message; no request sent |
| Malformed ID (fails client regex) | Inline error, e.g. "सही शिकायत क्रमांक डालें (जैसे SMD-0042)"; no request sent |
| `400 INVALID_COMPLAINT_ID` | Show the error body's `reply_text` (defense in depth — client validation should normally prevent this) |
| `404 COMPLAINT_NOT_FOUND` | Show the error body's `reply_text` ("such complaint not found") |
| Network failure / `5xx` | Generic Hindi retry message, same fallback pattern as `app.js`'s `send()` catch block |

## OUT OF SCOPE
Auto-refresh or polling (D-S15-4). Any change to the `GET /status` endpoint or `backend/` (already
built, S11). Showing `needs_review` differently from how `app.js` already shows it on the ticket
card (reuse, don't redesign). Linking *from* the chat page into this page, or vice versa — open,
see G-S15-2.

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S15-1 | Separate `status.html` + `status.js`, not a tab/section inside `index.html` | PROJECT.md §2 lists "status page" as its own scope item, distinct from the chatbot; keeps the chat flow (T21) untouched; matches the existing no-build, multi-file pattern |
| D-S15-2 | Client validates `complaint_id` format before calling the API | Avoids a guaranteed `400` for a typo the browser can already catch; same posture S11 applies server-side before its own DB call |
| D-S15-3 | Hindi status labels (`new`/`in_progress`/`resolved`/`needs_review` → Hindi strings) hardcoded in `status.js`, not shared with the dashboard's `labels.py` | No shared code exists between the Python backend/dashboard and vanilla-JS frontend; four stable enum values, same "duplication is fine here" reasoning `dashboard/src/dashboard/labels.py`'s own docstring gives for its 4 field labels |
| D-S15-4 | Single one-shot lookup per submit; no auto-refresh/polling | T22's done-when is just "shows status"; PROJECT.md §2 puts rate limiting/analytics-adjacent complexity in "Not now" |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S15-1 | `frontend/app.js`'s `API_BASE` still points at the T08 mock (`:8001`) even though T18 shipped the real `/message` route (`7104ff2`). `status.js` needs the same constant — confirm with Lead whether both files should now point at the real backend (`:8000`) or stay on the mock until T31 integration | Before T22 implementation |
| G-S15-2 | Should the status page be reachable from the chat page (header link, or a button after `action=submitted` pre-filled with the new `complaint_id`), or is it a separate URL citizens reach another way (e.g. from the ticket confirmation SMS/screenshot)? Not specified in PROJECT.md or TICKETS.md | Before T22 implementation |
| G-S15-3 | Confirm the four proposed Hindi status labels (D-S15-3) with Lead — only `needs_review`'s badge text ("समीक्षा के लिए भेजा गया", `app.js` line 73) currently exists as citizen-facing copy; `new`/`in_progress`/`resolved` have no precedent in the repo yet | Before T22 implementation |

## ACCEPTANCE
| Item | Covered by |
|---|---|
| Valid, existing complaint ID → status, department, updated time shown | §BEHAVIOR 3–4 |
| Malformed ID → inline error, no request | §BEHAVIOR 2, RULES §1 |
| Unknown but well-formed ID → citizen-safe "not found" message | §ERRORS |
| Scenario 9 (PROJECT.md §10 / S01 §10.2): officer sets "In progress" on the dashboard → this page shows `in_progress` | Trivially true once T24 (done) writes `tickets.status`; this page only reads (§BEHAVIOR 3–4) |
| No fields beyond the endpoint's four are ever displayed | RULES §3 |
