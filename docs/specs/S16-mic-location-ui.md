# S16 — Mic + Location in the Chat UI
Implements: T29 (`frontend/app.js`, `frontend/index.html`, `frontend/style.css`) · Depends on: S01
API contract §4.1 (multipart shape, D-A1/D-A8/D-A9), S12 Voice (backend side, already built) ·
Version: v1 · Status: Draft

## PURPOSE
T21 shipped a text-only chat page by deliberate scope split (S13's own precedent: "mic/GPS hardware
wiring belongs to T29, not T21"). This ticket adds the two remaining input modes S01 already
contracts for — recorded audio and a GPS location — to the existing chat page, using the same
`POST /api/v1/message` endpoint and the same response-rendering the text path already has.

## SCOPE
`frontend/app.js` (extended, not rewritten — the existing `sendToApi`/`send`/render functions are
generalised, not duplicated), `frontend/index.html` (two new composer buttons), `frontend/style.css`
(mic button states, reusing the hero's existing mic SVG and `--accent`/error tokens, no new palette).
Does not touch `backend/` (S12/T26 already built and live-verified), does not touch `status.html`
(T22, a separate read-only page with no input modes at all).

## BEHAVIOR

### 1. Recording audio
1. Click the mic button (idle state): request `navigator.mediaDevices.getUserMedia({audio: true})`.
2. On success: `new MediaRecorder(stream)` — **no explicit `mimeType` option**, so the browser picks
   its own default (Chrome/Firefox: `audio/webm`; Safari: `audio/mp4`) exactly as S12's own
   verification already covers (`EXT_BY_CONTENT_TYPE` in `backend/app/voice.py` has an entry for
   all four `ACCEPTED_AUDIO_TYPES`). Start recording; mic button switches to a visibly distinct
   "recording" state (RULES §3: colour is never the only signal — the button's `aria-label` and a
   text indicator change too, not just its colour).
3. Click the mic button again (recording state): `mediaRecorder.stop()`. On `onstop`, assemble the
   collected chunks into one `Blob` using `mediaRecorder.mimeType` (the browser's actual choice, not
   assumed), stop every track on the stream (releases the OS mic indicator), then send.
4. **Client-side type guard before upload**: normalise `mediaRecorder.mimeType` (strip codec
   parameters, e.g. `audio/webm;codecs=opus` → `audio/webm`) and check it against the same four
   types `ACCEPTED_AUDIO_TYPES` names (S01 §4.1) — mirrors the backend's own check
   (`api.normalise_content_type` / `ACCEPTED_AUDIO_TYPES` in `backend/app/schemas.py`) so an
   unsupported type is caught with a citizen-safe message locally, not as a round trip that ends in
   `415 UNSUPPORTED_AUDIO`.
5. Send: `FormData` with `session_id`, `message_id`, `audio` (the blob) — **never** a `text` field
   in the same request (S01 D-A1: one modality per turn; S01 4.1: "text and audio together are
   rejected"). `lat`/`lng` are not attached to an audio turn either — S01 doesn't forbid it, but
   nothing in this ticket's scope needs a citizen to record audio and share GPS in the same tap.
6. The citizen-facing bubble for this turn shows a placeholder (`🎤 आवाज़ भेजी जा रही है…`) immediately
   on send, then **is updated in place with the real `transcript`** once the response arrives (S01
   §4.2: `transcript` is only present for audio input) — so the citizen can see what the system
   actually heard, not just that something was sent. An empty/falsy `transcript` in the response
   leaves the placeholder as a fixed "(आवाज़ संदेश)" label instead (S01 D-A6: an empty transcript is
   `action=error`, not a client-side failure — the existing bot-reply rendering already shows the
   error message; this only concerns the citizen's own bubble text).

### 2. Sharing location
1. Click the location button: `navigator.geolocation.getCurrentPosition(...)`, no explicit text
   attached (S01 D-A8: "location may be sent alone; the location button needs no fake text
   message").
2. Success: `FormData` with `session_id`, `message_id`, `lat`, `lng` only. Citizen bubble:
   `📍 लोकेशन साझा की गई`.
3. Failure (permission denied, position unavailable, timeout, or `navigator.geolocation` absent):
   a citizen-safe Hindi message, **no request sent** — same "guard before the network call" posture
   S15 already established for status-ID format validation.

### 3. Contextual highlight (D-S16-1)
When a response's `ask_for === "location"` (S01 D-A4's whole stated purpose: "lets the UI show a
location button without holding logic"), the location button gets a highlighted visual state until
the next turn. It is never hidden the rest of the time — a citizen may share location proactively,
before being asked (S01 D-A8) — only *emphasised* when the bot just asked for it.

### 4. Shared response handling
`send()`'s existing action-rendering (`reply_text`, `confirm` → summary card, `submitted` → ticket
card, error handling) is factored into one function used by all three input modes (text, audio,
location) — S16 does not duplicate that logic three times, and does not change what it does for the
existing text path.

## RULES
1. Audio and text are never sent in the same request (S01 D-A1) — enforced structurally: the audio
   send path never reads or appends the textarea's value.
2. The recorded blob's type is checked against `ACCEPTED_AUDIO_TYPES` before any network call, same
   four types the backend accepts (S01 §4.1) — kept as one small constant in `app.js`, not
   duplicated backend logic re-implemented, just the same four literal strings the contract already
   fixes.
3. A status/error conveyed to the citizen is never colour-only (WCAG posture already used
   elsewhere in this repo — the pitch deck's own design pass, `dashboard`'s `needs_review` banner
   text-plus-colour) — the recording indicator changes text and `aria-label`, not just colour.
4. Every failure mode (mic permission denied, no `MediaRecorder` support, geolocation denied/
   unavailable/timeout, unsupported recorded type) shows a Hindi, citizen-safe message and leaves
   the composer usable — never a raw `DOMException`/browser error reaching `appendMessage` (the
   exact class of bug T50 already found and fixed for the network path; new code here must not
   reintroduce it for the media APIs).
5. The mic stream's tracks are always stopped after recording ends (success or failure) — never
   leave the browser's mic-in-use indicator on after a turn completes.

## ERRORS (client-side handling)
| Situation | UI behavior |
|---|---|
| `navigator.mediaDevices.getUserMedia` unsupported (very old/insecure-context browser) | Hindi message, no attempt made |
| Mic permission denied / no microphone found | Hindi message (`माइक्रोफ़ोन का उपयोग नहीं हो सका`), composer stays usable for typing |
| Recorded blob's type isn't one of the four accepted types | Hindi message, no upload attempted |
| `navigator.geolocation` unsupported | Hindi message, no attempt made |
| Geolocation permission denied / unavailable / timeout | Hindi message, no request sent |
| Backend `503`/network failure on an audio or location turn | Same `GENERIC_ERROR` fallback `app.js` already uses for text (T50) — not a new message |
| Backend `413 AUDIO_TOO_LARGE` / `415 UNSUPPORTED_AUDIO` | The error body's `reply_text`, same pattern as every other non-2xx response already handled |

## OUT OF SCOPE
- Any change to `backend/` — S12/T26 is already built and live-verified; this ticket only drives it
  from the browser.
- Audio playback of what was recorded before sending (no "preview and re-record" step) — record,
  stop, send, same posture as a voice-note app's simplest form.
- Visual waveform/level meter while recording — a text+colour "recording" state is enough for T29's
  own done-when ("Audio + GPS reach API"), not a polish ticket.
- Changing `status.html` (T22) in any way — it has no input modes to add mic/GPS to.
- A settings toggle for the browser's recording format — S12 D-S12-1 already means whatever the
  browser defaults to is accepted; nothing to configure.

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S16-1 | The location button is always visible, and only visually *highlighted* when `ask_for === "location"` — never hidden the rest of the time | S01 D-A8 explicitly allows sharing location unprompted; hiding the button between asks would contradict that, while S01 D-A4's own stated purpose (helping the UI know when to *show* it) is honoured as emphasis instead of visibility |
| D-S16-2 | No explicit `MediaRecorder` `mimeType` option — the browser's default is trusted and verified client-side against the same four accepted types the backend already checks | Matches S12 D-S12-1's whole premise (no FFmpeg, no format normalisation anywhere in the stack) — inventing a preferred format client-side would contradict that already-verified simplification |
| D-S16-3 | The citizen's own chat bubble for an audio turn is updated in place with the real transcript once the response returns, rather than left as a static placeholder | S01 §4.2 returns `transcript` specifically so a citizen can confirm what was understood; not showing it anywhere in the UI would waste a field the contract already provides for this exact purpose |
| D-S16-4 | Audio and location are two independent send paths, never combined in one request from this UI | S01 doesn't forbid `lat`/`lng` alongside `audio`, but nothing in T29's scope (mic button, location button) produces that combination — no reason to build a request shape nothing in this UI triggers |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S16-1 | No real citizen audio sample has yet produced a non-empty transcript from either Sarvam or Groq Whisper in this project (verified informally, not in `docs/problems/`) — this ticket's own live verification (recording a real Hindi sentence through this new UI) is the first genuine end-to-end attempt worth recording the outcome of, pass or fail | This ticket's Verification step |

## ACCEPTANCE
| Item | Covered by |
|---|---|
| TICKETS.md "Audio + GPS reach API" | §BEHAVIOR 1, 2 |
| Recorded audio and typed text are never sent together | RULES §1 |
| An unsupported recorded type never reaches the network | §BEHAVIOR 1 step 4, RULES §2 |
| Mic/geolocation permission denial shows Hindi text, not a raw browser error | ERRORS table, RULES §4 |
| Citizen's audio-turn bubble reflects the real transcript once known | §BEHAVIOR 1 step 6, D-S16-3 |
| Location button highlights when the bot asks for it, but is never the only way to send one | §BEHAVIOR 3, D-S16-1 |
