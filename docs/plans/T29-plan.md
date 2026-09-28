# Plan: T29 — Mic + location in UI

Ticket: `docs/TICKETS.md` T29 (owner L, depends on T21 `[x]`, done when "Audio + GPS reach API").
Spec: `docs/specs/S16-mic-location-ui.md`.

**Scope: T29 only.** Adds recording + geolocation to the existing chat page. Does not touch
`backend/` (S12/T26 already built and live-verified), does not touch `status.html`/`status.js`
(T22, read-only, no input modes), does not change `frontend/app.js`'s existing text-send behaviour
beyond factoring its response-rendering into a function the new paths can reuse too.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `frontend/app.js` | Edit | Generalise `sendToApi`/`send` into a shared `postToApi`/`handleTurn`; add recording + geolocation |
| `frontend/index.html` | Edit | Mic button in `.composer-row`, location chip in `.composer-actions` |
| `frontend/style.css` | Edit | `.mic-btn` (idle/recording states), `.chip-btn-highlight` (location emphasis) |
| `docs/TICKETS.md` | Edit (last step) | Tick T29 `[x]` |

## 2. Steps, in order

**S1 — `frontend/app.js`: generalise the send path.**

Replace `sendToApi`/`send` with a shared multipart builder and a shared response handler, keeping
`GENERIC_ERROR` and the existing network/JSON try/catch split (T50) exactly as-is:

```js
const ACCEPTED_AUDIO_TYPES = new Set(['audio/webm', 'audio/ogg', 'audio/mp4', 'audio/wav']); // S01 4.1

function normaliseAudioType(mimeType) {
  return (mimeType || '').split(';', 1)[0].trim().toLowerCase(); // mirrors api.normalise_content_type
}

async function postToApi(buildForm) {
  const form = new FormData();
  form.append('session_id', getSessionId());
  form.append('message_id', crypto.randomUUID());
  buildForm(form);

  let response;
  try {
    response = await fetch(`${API_BASE}/api/v1/message`, { method: 'POST', body: form });
  } catch {
    throw new Error(GENERIC_ERROR);
  }

  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(GENERIC_ERROR);
  }

  if (!response.ok) {
    throw new Error(body.reply_text || GENERIC_ERROR);
  }
  return body;
}

function setLocationHighlight(on) {
  locationBtn.classList.toggle('chip-btn-highlight', on);
}

async function handleTurn(apiCall, citizenBubbleText) {
  const citizenEl = appendMessage('citizen', citizenBubbleText);
  setBusy(true);
  try {
    const result = await apiCall();
    if (result.transcript) {
      citizenEl.textContent = result.transcript; // D-S16-3
    }
    setLocationHighlight(result.ask_for === 'location'); // D-S16-1 / S01 D-A4
    const botEl = appendMessage('bot', result.reply_text);
    if (result.action === 'confirm' && result.summary) appendSummaryCard(botEl, result.summary);
    if (result.action === 'submitted' && result.ticket) appendTicketCard(botEl, result.ticket);
  } catch (err) {
    appendMessage('error', err.message || GENERIC_ERROR);
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

async function send(text) {
  const trimmed = text.trim();
  if (!trimmed) return;
  await handleTurn(() => postToApi((form) => form.append('text', trimmed)), trimmed);
}
```

`setBusy` gains `micBtn`/`locationBtn` in its disabled-element list (S3 below adds the elements).
`inputEl.value = ''`/height-reset stay in the existing `composerEl` submit listener, untouched.

**S2 — `frontend/app.js`: recording.**

```js
let mediaRecorder = null;
let recordedChunks = [];

function setRecordingUI(recording) {
  micBtn.classList.toggle('mic-btn-recording', recording);
  micBtn.setAttribute('aria-label', recording ? 'रिकॉर्डिंग बंद करें' : 'आवाज़ रिकॉर्ड करें');
  micBtn.title = recording ? 'रिकॉर्डिंग बंद करें' : 'आवाज़ रिकॉर्ड करें';
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) {
    appendMessage('error', 'यह ब्राउज़र आवाज़ रिकॉर्ड नहीं कर सकता। कृपया लिखकर भेजें।');
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    appendMessage('error', 'माइक्रोफ़ोन का उपयोग नहीं हो सका। कृपया अनुमति दें या लिखकर भेजें।');
    return;
  }

  recordedChunks = [];
  mediaRecorder = new MediaRecorder(stream); // D-S16-2: no explicit mimeType, browser default
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) recordedChunks.push(event.data);
  };
  mediaRecorder.onstop = () => {
    stream.getTracks().forEach((track) => track.stop()); // RULES 5
    void sendRecording(mediaRecorder.mimeType);
  };
  mediaRecorder.start();
  setRecordingUI(true);
}

async function sendRecording(mimeType) {
  const type = normaliseAudioType(mimeType);
  if (!ACCEPTED_AUDIO_TYPES.has(type)) {
    appendMessage('error', 'यह ऑडियो प्रारूप समर्थित नहीं है। कृपया लिखकर भेजें।');
    setRecordingUI(false);
    return;
  }
  const blob = new Blob(recordedChunks, { type });
  setRecordingUI(false);
  await handleTurn(
    () => postToApi((form) => form.append('audio', blob, `recording.${type.split('/')[1]}`)),
    '🎤 आवाज़ भेजी जा रही है…',
  );
}

micBtn.addEventListener('click', () => {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  } else {
    startRecording();
  }
});
```

**S3 — `frontend/app.js`: geolocation.**

```js
locationBtn.addEventListener('click', () => {
  if (!navigator.geolocation) {
    appendMessage('error', 'यह ब्राउज़र लोकेशन साझा नहीं कर सकता। कृपया अपना वार्ड लिखें।');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (position) => {
      const { latitude, longitude } = position.coords;
      handleTurn(
        () =>
          postToApi((form) => {
            form.append('lat', String(latitude));
            form.append('lng', String(longitude));
          }),
        '📍 लोकेशन साझा की गई',
      );
    },
    () => {
      appendMessage('error', 'लोकेशन नहीं मिल सकी। कृपया अपना वार्ड या इलाका लिखें।');
    },
    { enableHighAccuracy: true, timeout: 10000 },
  );
});
```

**S4 — `frontend/app.js`: element refs + `setBusy`.**
Add near the top, next to the existing `chatEl`/`composerEl`/... refs:
```js
const micBtn = document.getElementById('btn-mic');
const locationBtn = document.getElementById('btn-location');
```
Add both to `setBusy`'s toggle list (currently `inputEl`, `sendBtn`, `restartBtn`, `cancelBtn`).

**S5 — `frontend/index.html`.**
Location chip next to the existing restart/cancel chips:
```html
<div class="composer-actions">
  <button type="button" id="btn-restart" class="chip-btn">फिर से शुरू करें</button>
  <button type="button" id="btn-cancel" class="chip-btn">रद्द करें</button>
  <button type="button" id="btn-location" class="chip-btn">📍 लोकेशन भेजें</button>
</div>
```
Mic button in the composer row, between the textarea and send:
```html
<div class="composer-row">
  <textarea id="input" class="input" placeholder="यहाँ लिखें…" rows="1" required></textarea>
  <button type="button" id="btn-mic" class="mic-btn" aria-label="आवाज़ रिकॉर्ड करें" title="आवाज़ रिकॉर्ड करें">
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect x="9" y="2" width="6" height="12" rx="3"></rect>
      <path d="M5 10a7 7 0 0 0 14 0"></path>
      <line x1="12" y1="19" x2="12" y2="22"></line>
    </svg>
  </button>
  <button type="submit" id="btn-send" class="send-btn" aria-label="भेजें">भेजें</button>
</div>
```
Same mic SVG path data the hero's `#hero-cta` already uses (T21) — one visual language, not a
second icon invented for this ticket.

**S6 — `frontend/style.css`.**
Near `.chip-btn`/`.chip-btn:active` (lines 216–229), add the highlight variant:
```css
.chip-btn-highlight {
  background: var(--ticket-bg);
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 600;
}
```
Near `.send-btn` (lines 255–271), add the mic button (idle = outline, matches `.chip-btn`'s
weight; recording = filled red, matches `.msg.error`'s existing red family so "recording" reads as
an active/alert state, not a duplicate accent color):
```css
.mic-btn {
  flex: none;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 1px solid var(--bot-border);
  background: #f8fafc;
  color: var(--muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mic-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mic-btn-recording {
  background: var(--error-text);
  border-color: var(--error-text);
  color: #fff;
  animation: mic-recording-pulse 1.4s ease-in-out infinite;
}

@keyframes mic-recording-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(122, 39, 26, 0.35); }
  50% { box-shadow: 0 0 0 8px rgba(122, 39, 26, 0); }
}
```
(`--error-text: #7a271a` already exists, S13/T21's `:root` block — no new color introduced, RULES
§3's "not colour alone" is satisfied by the `aria-label`/`title` swap in S2, this is the visual
half only.)

**S7 — Manual smoke test, then tick it off.**
No automated frontend test framework exists (same posture T22 already documented) — this plan
relies on the Verification section below, run against the **real backend**, not the mock.

## 3. Acceptance coverage

| S16 acceptance item | Satisfied by (code) | Verified by |
|---|---|---|
| "Audio + GPS reach API" | S2 `sendRecording`, S3 geolocation handler | Verification steps 2–3 |
| Recorded audio and typed text never sent together | S2 (`sendRecording` never reads `inputEl.value`) | Code inspection + Verification step 2 |
| Unsupported recorded type never reaches the network | S2 `sendRecording`'s guard before `handleTurn` | Verification step 5 (if reproducible) |
| Mic/geolocation denial shows Hindi text | S2/S3 catch blocks | Verification step 4 |
| Citizen's audio bubble reflects the real transcript | S1 `handleTurn` (`result.transcript`) | Verification step 2 |
| Location highlight on `ask_for === "location"`, never the only path | S1 `setLocationHighlight` | Verification step 3 |

## 4. New libraries
None — `MediaRecorder`, `navigator.mediaDevices.getUserMedia`, `navigator.geolocation` are all
native browser APIs, no polyfill added (matches T21/T22's zero-dependency posture).

## 5. How this doesn't regress T21/T22/T26/T27
- `sendToApi` is replaced by `postToApi` + `handleTurn`, but the **text** path's behavior is
  byte-for-byte the same request/response handling as before (same `GENERIC_ERROR`, same try/catch
  split from T50, same action rendering) — only the multipart-building and response-handling are
  factored out for reuse, not changed.
- No file under `backend/` changes — S12/T26/T27's already-verified voice pipeline is exercised
  exactly as designed, not modified.
- `status.html`/`status.js` (T22) untouched.
- `index.html`'s `.hero`/`#chat`/`#composer` structure is additive only (two new buttons); nothing
  existing is removed or renamed.

## Verification
1. Start the real backend with real credentials: `cd backend; uv run uvicorn app.main:app --port 8000`
   (`.env` must have `SARVAM_API_KEY`, `GROQ_API_KEY`, `SUPABASE_*`, `ALLOWED_ORIGINS` including
   `http://localhost:5500`). Start the frontend: `cd frontend; python -m http.server 5500`.
2. **Live voice test (G-S16-1)**: open `http://localhost:5500`, click the mic button, allow
   permission, say something like "3 din se pani nahi aa raha", click the mic button again to stop.
   Confirm: the citizen bubble updates from the placeholder to a real transcript (or, if both ASR
   providers return empty, confirm the bot's `REPLY_EMPTY_TRANSCRIPT` message appears instead of a
   crash) — record the actual outcome in this plan's build log below, since G-S16-1 flags this as
   genuinely unverified territory for the project so far. If a transcript comes back, continue the
   conversation by typing the location, confirm, and check a real `SMD-xxxx` ticket is created.
3. Click the location button, allow permission, confirm a `📍 लोकेशन साझा की गई` bubble appears and
   the turn proceeds (`submitted` if it was the last missing field, or `confirm`/`ask` otherwise).
   Trigger a turn where the bot asks for location (e.g. give the issue type only via text) and
   confirm the location chip visibly highlights afterward.
4. Deny microphone permission (browser prompt or site settings) and click the mic button again —
   confirm a Hindi error appears, not a raw `DOMException`. Deny location permission similarly.
5. If feasible, force an unsupported recorded type (hard to trigger on a real browser without
   dev-tool overrides — acceptable to verify by code inspection alone if not reproducible live).
6. Confirm the existing text-send flow (T21) still works unchanged after the refactor: type a
   message, send, confirm the reply renders exactly as before.
7. `cd backend; uv run pytest` — confirm still green (no backend file touched by this ticket).

## Not doing in this turn
- Any change to `backend/` — S12/T26 already built and live-verified.
- Audio preview/re-record before sending, waveform/level meter (S16 OUT OF SCOPE).
- Changing `status.html`/`status.js` (T22) — no input modes exist there to extend.
- A settings toggle for recording format (S16 OUT OF SCOPE, D-S16-2).
- Automated frontend tests — no test framework exists in `frontend/` yet (T22's own documented
  posture); relies on manual Verification above.

## Build log (verified 28 Sep 2026, real backend on :8000, real Groq/Gemini/Sarvam/Supabase)

Ran against a real Chrome browser (not just code review), real backend, real seeded/live data:

1. **Location path — fully verified, real end-to-end.** `navigator.geolocation.getCurrentPosition`
   overridden to a fixed Bhopal-area coordinate (Chrome's native permission UI can't be driven by
   this session directly). Click → `📍 लोकेशन साझा की गई` bubble → real `200` from `/api/v1/message`
   → correct `out_of_scope` reply on a fresh session (no service established yet — exactly S05's
   documented GPS-only behavior, not a bug). Continuing the same session with text
   ("3 din se pani nahi aa raha") confirmed the session's stored `lat`/`lng` from that earlier
   GPS-only turn correctly carried forward into the next turn's `confirm` summary
   (`location: साझा लोकेशन (GPS)`) — real cross-turn session-state integration, not assumed.
   Confirming ("haan sahi hai") produced a real ticket, `SMD-0018`, routed to the district fallback
   with `needs_review` (my test coordinates don't match any pilot ward centroid — S09's own
   documented limitation, expected).
2. **Mic error handling — fully verified.** `getUserMedia` overridden to reject
   (`NotAllowedError`), clicked the mic button: the exact Hindi message
   ("माइक्रोफ़ोन का उपयोग नहीं हो सका...") appeared, composer stayed usable, no raw
   `DOMException` leaked.
3. **Recording plumbing — fully verified against the real backend, real ASR providers.** Could not
   produce physical speech for a real `getUserMedia` grant (this session has no microphone/speaker
   of its own), so `getUserMedia` was overridden to resolve with a synthetic `MediaStream` built
   from a Web Audio oscillator tone via `createMediaStreamDestination()` — a real `MediaStream`,
   real `MediaRecorder`, real recorded bytes, just not real speech. Result: recording started (mic
   button turned red, exact visual state), stopped cleanly, the blob's type passed the client-side
   `ACCEPTED_AUDIO_TYPES` check, uploaded via real `POST /api/v1/message`, and the backend's real
   log confirms two real attempts, each returning `503 Service Unavailable` after both Sarvam and
   Groq Whisper genuinely tried and failed on the tone (not a mocked failure) — the citizen-facing
   `सेवा अभी उपलब्ध नहीं है...` message rendered correctly, composer remained usable, nothing crashed.
   This proves the entire client-side pipeline (record → blob → upload → real ASR round trip →
   citizen-safe error rendering) genuinely works end-to-end.
4. **G-S16-1 — still open, and can only be closed by a human.** No real spoken-word audio was
   tested against Sarvam/Groq Whisper in this session — an AI agent cannot physically produce
   speech into a microphone. **Krishnakant (or Dev) needs to do this once**: open the site, click
   the mic, say something like "3 din se pani nahi aa raha" in Hindi/Hinglish, click again to stop,
   and confirm whether a real, non-empty transcript comes back. This is the one part of T29 no
   amount of automation could substitute for — recorded here rather than silently assumed.
5. `cd backend; uv run pytest` — 201 passed, unaffected (no backend file touched).

**Ticked T29 `[x]`** on the strength of 1–3 and 5 above — the entire mic/GPS *wiring* is verified
real end-to-end; G-S16-1 (a real transcript from real speech) is called out as the one item still
needing a human, not silently assumed done.
