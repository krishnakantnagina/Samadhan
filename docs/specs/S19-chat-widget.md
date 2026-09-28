# S19 — Floating Chat Widget (reusable, for pages without the full chat)
Implements: T53 (`frontend/widget.js`, `frontend/style.css`, `frontend/status.html`) · Depends on:
S01 API contract §4.1/§8 (unchanged), S15 status page (first host page), S16 mic/location, S17
TTS, S18 press-and-hold + greeting (widget now mirrors all three in full, see REVISION) ·
Version: v1 · Status: Draft

## REVISION (same day, direct instruction: "fully equivalent... in functionality and behavior")
The original v1 scope (§SCOPE, RULES §1 below) was deliberately text-only. That's now superseded:
the widget mirrors `app.js`'s **full** feature set — press-and-hold voice (S16/S18), GPS location
with the same `ask_for`-highlight behavior, TTS speak buttons on every bot bubble (S17),
restart/cancel commands, and the same delayed bilingual auto-play greeting (S18 BEHAVIOR 4) — not
just text send. RULES §1 and the "text-only" framing throughout the original spec below are
superseded by this revision; kept in place rather than rewritten so the reasoning trail (why v1
was scoped narrow, then wasn't) stays legible. D-S19-2 (duplicate, don't share, with `app.js`)
applies more heavily now — `widget.js` is a near-full mirror of `app.js`'s logic against its own
namespaced DOM, still with zero imports, for the same no-build-step reason.

## PURPOSE
`frontend/index.html` already *is* the full chat experience (T21/T29/T51/T52) — no widget needed
there. Other pages (today: `status.html`; potentially more later) have no way to reach the bot at
all except a link back to `index.html`. This adds a small, real, reusable floating chat widget —
same real backend, not a mockup — that can be dropped onto any page with one `<script>` include.

## SCOPE
A self-mounting `frontend/widget.js` (injects its own DOM on load, no HTML placeholder needed) +
shared additions to `frontend/style.css` (reuses existing `.msg`/bubble/token classes for visual
consistency with the full chat page, rather than a separate design language). Added to
`status.html` only, per explicit scope decision — **not** added to `index.html` (redundant: the
whole page is already the chat) and not added to the dashboard (different audience, out of scope
per every prior ticket's own boundary). Text-only: no voice, no GPS, no TTS in the widget — the
brief for this ticket asked for "User/AI messages," not a second implementation of T29/T51's
richer input modes. A citizen who wants voice already has the full page one click away.

## BEHAVIOR
1. A floating round button, fixed bottom-right, present on any page that includes the script. A
   small label pill ("💬 सहायता चाहिए? · Need help?") sits beside it until first opened, then never
   reappears this session (`sessionStorage` flag) — icon-alone buttons are exactly the
   discoverability problem T52's brief flagged for a first-time villager user; this widget is a
   secondary entry point, so it gets one chance to be found, not a permanent icon-only guess.
2. Click → the panel opens with a scale+fade-in animation (~220ms, `prefers-reduced-motion`
   respected); the button's icon swaps from a chat bubble to a close (×) glyph. Click again (or the
   panel's own × in its header) → closes with the reverse animation. State is not persisted across
   reloads — every page load starts closed.
3. On first open only, a single short Hindi bot line renders ("नमस्ते! मैं समाधान हूँ। अपना सवाल
   यहाँ लिखिए।") — not T52's full bilingual greeting card (out of scope for a small panel; the full
   page already owns that experience).
4. Sends real text turns via `POST /api/v1/message`, exactly the same `FormData` shape and
   `session_id`/`message_id` scheme `app.js`'s `postToApi` already uses (S16) — including reusing
   the **same** `sessionStorage` key (`samadhan_session_id`). A citizen who was mid-conversation on
   `index.html` and opens the widget elsewhere in the same tab continues that exact session,
   server-side state and all — not a new, disconnected conversation (D-S19-1).
5. Renders `reply_text`, `confirm` → summary, `submitted` → ticket, exactly the same rendering
   rules `handleTurn`/`appendSummaryCard`/`appendTicketCard` already implement — this spec does not
   reinvent that logic, it reuses the same *shape* of response handling, duplicated into
   `widget.js` since the widget must work on a page that never loads `app.js` (S8 below explains why
   duplication, not a shared module, was chosen).
6. Every failure mode (network down, malformed response, non-2xx) shows the same Hindi
   `GENERIC_ERROR`-class citizen-safe message `app.js` already uses (T50's fix) — never a raw
   browser/JS error. `fetch()` and `.json()` parsing are each wrapped separately, identically to
   `postToApi`'s own pattern.

## RULES
1. Text-only. The widget must not attempt audio recording, geolocation, or TTS — out of scope
   (§SCOPE). If this needs to change later, that's a new ticket, not a silent scope creep here.
2. Never `innerHTML` on anything network-derived (`reply_text`, `department`, office names, summary
   values) — same discipline every other frontend file in this repo already holds to.
3. The widget must not alter or read any state belonging to the host page's own scripts
   (`status.js` on `status.html` today) — it is purely additive, self-contained, namespaced DOM
   (`#samadhan-widget-*` ids/classes) so it can never collide with a host page's own elements.
4. Same `API_BASE` convention as every other frontend file (`http://localhost:8000`, a plain
   top-of-file constant) — defined locally in `widget.js`, not imported from `app.js`, since a host
   page may not load `app.js` at all.

## ERRORS
| Situation | UI behavior |
|---|---|
| `fetch()` throws (network/CORS/offline) | `GENERIC_ERROR`, same Hindi text as `app.js` |
| Non-JSON or malformed response body | `GENERIC_ERROR` |
| Non-2xx response | The body's `reply_text` if present, else `GENERIC_ERROR` — same as every other endpoint in this project (S01 §7) |

## OUT OF SCOPE
- Voice recording, GPS location, TTS speak buttons — text-only widget (RULES §1).
- Adding the widget to `index.html` (redundant) or the dashboard (wrong audience).
- A shared/imported module between `app.js` and `widget.js` — see D-S19-2 for why light
  duplication was chosen over a shared file for this specific, small amount of logic.
- Persisting open/closed panel state across page loads or across pages.
- Unread-message badges, sound notifications, or any engagement-optimization pattern — this is a
  citizen-service tool, not a marketing chat widget; it should be easy to find once, not naggy.

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S19-1 | The widget reuses the exact same `sessionStorage` key as `app.js` (`samadhan_session_id`) | A citizen's in-progress conversation is server-side state keyed by `session_id` (S06); there is no reason a second entry point in the same browser tab should start a disconnected new session instead of continuing the same one |
| D-S19-2 | `widget.js` duplicates (not imports) the small slice of request/response logic it needs from `app.js`, rather than extracting a shared module | The two files currently have zero build step and zero module system (T52's own stated constraint, "no framework, no build step"); introducing an ES module/bundler just to share ~40 lines between two files is a bigger change than the duplication it would avoid. The duplicated logic is small, stable (S01's contract), and already has a single source of truth in `app.js`'s own comments referencing the spec |
| D-S19-3 | A discoverability label pill shown once per session, not permanently | Balances T52's "icon alone is ambiguous to a first-time user" concern against not permanently cluttering the corner of every page with a floating text label once the citizen already knows what the button does |

## ACCEPTANCE
| Item | Covered by |
|---|---|
| Floating button, bottom-right, present on `status.html` | §BEHAVIOR 1 |
| Open/close animation | §BEHAVIOR 2 |
| Modern chat interface, consistent with the rest of the site | §SCOPE (reuses `.msg`/bubble styles) |
| Real user/AI messages, not mocked | §BEHAVIOR 4–5 |
| No raw browser/JS error ever shown | §BEHAVIOR 6, RULES §2 |
| `index.html`/dashboard untouched | §SCOPE |
