# S18 — Citizen UI Redesign: Press-and-Hold Voice + Villager-First Visual Language
Implements: T52 (`frontend/app.js`, `frontend/index.html`, `frontend/style.css`) · Depends on: S01
API contract §4.1 (unchanged), S16 mic/location wiring (behavior mostly preserved, trigger
replaced), S17 TTS speak button (preserved, unstyled changes only) · Version: v1 · Status: Draft

## PURPOSE
`docs/T52-designer-brief.md` is the actual product brief (read it first — this spec only pins down
the concrete interaction/technical decisions the brief deliberately left open: exact gesture
implementation, the cancel-on-short-press threshold, what survives from S16's request/response
plumbing vs. what's replaced, how much of the existing visual system carries forward). Two hard
requirements from the brief: (1) replace tap-to-toggle recording with WhatsApp-style press-and-hold,
(2) show the exact bilingual greeting copy, verbatim, as the opening message.

## SCOPE
`frontend/app.js` (the recording *trigger* is replaced; `postToApi`/`handleTurn`/`sendRecording`'s
request-building survive unchanged — S16's plumbing was never the problem, its `click`-to-toggle
event wiring was), `frontend/index.html` (mic button restructured, larger; composer layout), and
`frontend/style.css` (new visual language: bigger tap targets, mic button as the dominant element,
greeting card, message-arrival and ticket-confirmation micro-interactions). Does not touch
`backend/`, `dashboard/`, `frontend/status.html`/`status.js` (brief: "unless the redesign
specifically calls for extending it... check with Lead first" — nothing here requires it, S18 does
not touch the status page).

## BEHAVIOR

### 1. Press-and-hold recording (replaces S16 BEHAVIOR §1 steps 1–3 only; steps 4–6 unchanged)
1. `pointerdown` on the mic button → `micBtn.setPointerCapture(event.pointerId)` (so a finger
   sliding slightly off the button during the hold still delivers `pointerup` to this button,
   standard practice for press-and-hold controls) → record `holdStartedAt = performance.now()` →
   begin `getUserMedia` immediately. Visual state changes to "starting" (see RULES §3) the instant
   the finger goes down — the citizen must see *something* happen immediately, not wait for the
   permission round-trip.
2. Once the stream is granted and `MediaRecorder` actually starts (same S16 D-S16-2 posture: no
   explicit `mimeType`), visual state changes to "recording": a growing/pulsing ring, a live
   `mm:ss` timer, and the text "रिकॉर्ड हो रहा है… छोड़ने पर भेजा जाएगा" ("Recording… release to
   send") — RULES §2 covers why text, not colour alone.
3. `pointerup` (or `pointercancel` — OS interrupt, app backgrounded, etc.) on the mic button:
   - If the finger released *before* the recorder had actually started (permission prompt still
     pending — realistic on a first use), remember the release and finalize as a cancel the moment
     the stream would otherwise have started, rather than starting a recording nobody is still
     holding for.
   - Compute `held = performance.now() - holdStartedAt`. If `held < MIN_HOLD_MS` (400ms, D-S18-1):
     **cancel** — stop the recorder without sending, stop every track (S16 RULES §5 unchanged), show
     a brief neutral inline state on the mic button itself (not a new chat bubble — a cancelled tap
     is not a failed turn, same posture S17 already established for a failed "listen" tap), then
     return to idle.
   - Otherwise: stop the recorder normally; `onstop` calls the existing `sendRecording(mimeType)`
     unchanged from S16.
4. No slide-to-cancel-by-moving-off-the-button gesture (brief: explicitly "nice to have, not
   required" — OUT OF SCOPE).

### 2. The greeting (replaces the single-line bot bubble `send`/`appendMessage` currently opens with)
A new `appendGreeting()` renders one bot-styled card, appended on page load exactly where the old
`appendMessage('bot', 'नमस्ते!...')` call was, containing — **verbatim, both languages, Hindi
first** (brief's own suggested pattern, "Hindi-primary with an English line underneath"):

> नमस्ते! मैं समाधान हूँ।
> आप अपनी समस्या हमें बताइए, या किसी भी सरकारी सेवा से जुड़ी जानकारी चाहिए तो बेझिझक पूछिए।
> आप अपनी बात **आवाज़ में बोलकर या लिखकर** बता सकते हैं। हम आपकी सहायता करने की पूरी कोशिश करेंगे।
>
> Hello! I'm Samadhan.
> Please tell me about your problem, or ask me if you need information about any government
> service.
> You can **speak your message or type it**. We'll do our best to help you.

Built with `createElement` throughout (this is static, developer-authored copy, never
network-derived — but the file's existing discipline is "never `innerHTML`, anywhere," and a
special-cased exception here is exactly the kind of thing a future edit could misapply to actually
risky content; kept uniform instead). The two bolded phrases become `<strong>` elements.

### 3. Visual redesign (the parts of the brief that are genuinely a design call, pinned down here)
- **Mic button is the single largest, most obvious composer element** (brief, verbatim): grown from
  the current 44px circle to an 88px circle (D-S18-2), visually dominant against the 52px-tall text
  row beside it.
- **Every touch target ≥ 48px**: mic 88px, send/location/restart/cancel/input all raised from their
  current 44px/13px-font footprint to a 52px-minimum height, 15px-minimum font (RULES §1).
- **Icon+text, never icon-alone**: the mic button gains a persistent caption beneath the composer
  ("🎤 बोलने के लिए दबाकर रखें · Hold to speak") rather than relying on its `aria-label` alone — the
  brief's "an icon alone is ambiguous to a first-time user" applies to *every* first-time user, not
  just assistive-tech ones.
- **Message-arrival micro-interaction**: new bot/citizen bubbles fade+rise in (reuses the existing
  `.reveal`/`reveal-up` keyframe pattern already established in the hero section, not a new
  animation vocabulary), respecting `prefers-reduced-motion` exactly as the hero already does.
- **Idle-state mic breathing**: a slow, subtle pulse on the mic button at rest (distinct in both
  timing and colour from the urgent red "recording" pulse it already has) — signals "this is alive
  and tappable" without implying anything is currently happening.
- **Ticket-confirmation micro-interaction**: the ticket card (`appendTicketCard`) gets a brief
  scale-in + colour-settle on arrival — the one moment in the flow that deserves to feel
  celebratory, per the brief's "satisfying confirmation animation when a ticket is created."
- **Palette unchanged** (brief: keep unless a strong reason not to — none found; navy `#0F2A4A` /
  accent `#2563EB` / off-white `#FBFBF8` already match the pitch deck). Only new `--*` tokens this
  spec adds are for the two new interaction states above, built from existing hues, not new ones.

## RULES
1. No touch target smaller than 48px in any dimension (brief's explicit floor; this spec uses 52px
   as the working minimum for anything not the mic button itself, to leave visible breathing room
   above the stated floor).
2. Every state change (recording, cancelled, error) is signalled by text/label change, never colour
   alone — S16 RULES §3's WCAG posture, extended to the new "starting"/"cancelled" states this spec
   adds.
3. S16 RULES §4/§5 (every failure mode shows Hindi text, never a raw browser error; mic tracks
   always stopped after recording ends, success or failure) are unchanged and apply identically to
   the new press-and-hold trigger — this is exactly the bug class `docs/problems/T50-app-js-network-
   fallback.md` already found twice; the *trigger* changes, the *safety net* around it does not.
4. `postToApi`, `handleTurn`, `sendRecording`, the location-button logic, and the TTS speak button
   (S17) are **not modified in their request-building or response-handling logic** — only their
   surrounding markup/CSS classes, where the redesign requires it (e.g. a bigger button). A
   behavioral diff in any of these outside what this spec calls for is a regression, not a
   redesign.

## ERRORS (new states this spec adds; S16's existing ERRORS table is otherwise unchanged)
| Situation | UI behavior |
|---|---|
| Release before `MIN_HOLD_MS` (400ms) elapsed | Cancel silently-ish: brief neutral mic-button state ("रद्द" for ~1s, same flash pattern S17's speak-button failure state already uses), no chat bubble, no request sent |
| Release before the recorder had actually started (permission prompt still pending) | Same cancel path, applied the moment the stream would otherwise have started |
| Mic permission denied / no `MediaRecorder` support / unsupported recorded type / geolocation failure | Unchanged from S16 — same Hindi messages, same citizen-safe posture |

## OUT OF SCOPE
- Slide-up-to-cancel while holding (brief: optional, not required; deferred — G-S18-1).
- A visible waveform/level meter during recording (S16's own precedent: a text+colour state is
  enough; this spec adds a timer on top of that, not a waveform).
- Any change to `status.html`/`status.js`, `backend/`, or `dashboard/`.
- A framework or build step (brief: discuss with Lead first if genuinely believed necessary; not
  proposed here — the existing vanilla-JS approach handles pointer events and DOM-building fine at
  this scope).
- A language toggle for the greeting (both languages are shown together, always — brief: "just
  don't lose either version," not "let the citizen pick one").
- Caching/persisting whether a citizen has already seen the greeting (it reappears every page load,
  same as the current single-line greeting already does — no new session-state needed).

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S18-1 | `MIN_HOLD_MS = 400` | Long enough that a genuine accidental tap (typically well under 200ms) reliably cancels, short enough that a citizen deliberately saying even one short word isn't cancelled against their intent. Not user-tested (no real users available to this session) — flagged as a PROPOSED value, easy to retune (one constant) if real usage shows otherwise (G-S18-2) |
| D-S18-2 | Mic button grown to 88px (vs. the previous 44px) | Brief: "the single largest, most obvious element on the screen." 88px keeps it clearly dominant over the 52px text row without dominating the whole viewport on small phones |
| D-S18-3 | Pointer Events (`pointerdown`/`pointerup`/`pointercancel`) instead of separate touch/mouse handlers | One code path for touch, mouse, and pen; `setPointerCapture` gives reliable release-tracking even if the finger drifts slightly during the hold, without needing to hand-roll touch-move-tracking |
| D-S18-4 | Greeting built with `createElement`/`<strong>`, not `innerHTML` | Static copy is technically safe to inline, but this file has zero `innerHTML` calls anywhere today; a carve-out here is a precedent a future edit could misapply to genuinely risky (network-derived) content. Consistency over a few lines saved |
| D-S18-5 | Cancelled-recording state reuses the speak-button's existing brief-inline-flash pattern (text change, auto-revert after ~1s), rather than inventing a new transient-state UI pattern | One flash-state idiom in the codebase, not two doing the same job differently |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S18-1 | Slide-up-to-cancel deferred per brief's own "nice to have" framing — revisit if real usage shows accidental long-holds are a problem `MIN_HOLD_MS` alone doesn't solve | Post-T52, if ever |
| G-S18-2 | `MIN_HOLD_MS = 400` is a PROPOSED value (D-S18-1), never tuned against a real user's actual tapping behavior | Before demo day, ideally with real village-user testing per the brief's own "Real-device testing" deliverable |
| G-S18-3 | **Partially resolved during this ticket's own verification.** Querying the real DB directly while testing found that G-S16-1 was already closed out since T29 shipped: a real human-spoken conversation exists (session `3687e879-...`, six real turns, real non-empty Hindi transcripts, ending in a real submitted ticket `SMD-0019`) — proving real speech → real transcript → real ticket works end-to-end, via the pre-T52 tap-to-toggle gesture. Still open: that conversation used the *old* gesture, not the new press-and-hold one this ticket ships; this session's own live test of the new gesture (synthetic `MediaStream`/pointer events, an AI agent still can't physically speak) reused `sendRecording`/`postToApi` unchanged from S16, so identical behavior is expected but not yet directly observed with a human speaking through the *new* button specifically | Nice-to-have before demo day, not blocking — the underlying pipeline is proven |
| G-S18-4 | **Found and fixed during verification**, not anticipated when this spec was drafted: `micBtn.setPointerCapture(event.pointerId)` can throw `NotFoundError` for a pointer id the browser doesn't recognize as currently active. Real touch/mouse input always has a valid active pointer at `pointerdown` time, so this should never trigger for a real citizen — but it was uncaught, and an uncaught exception in the `pointerdown` handler would have silently stopped `beginHold()` from ever running (the mic button would just do nothing, no citizen-facing error at all). Fixed with a `try`/`catch` around the capture call alone; recording now proceeds regardless of whether capture succeeds | Already fixed, this session |

## ACCEPTANCE
| Brief's item | Covered by |
|---|---|
| Press-and-hold works exactly like WhatsApp: hold = record, release = send, short tap cancels | §BEHAVIOR 1 |
| Greeting shows both English and Hindi, verbatim | §BEHAVIOR 2 |
| Large tap targets, icon+text everywhere, Hindi-first | §BEHAVIOR 3, RULES §1 |
| Every existing flow still works (text, voice, GPS, 🔊 listen, status page) | RULES §4 |
| No raw browser/JS error ever reaches a citizen | RULES §3 |
| Palette kept, no framework introduced silently | §BEHAVIOR 3 (palette), OUT OF SCOPE (framework) |
