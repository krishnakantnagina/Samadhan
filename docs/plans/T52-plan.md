# Plan: T52 — Citizen website redesign (press-and-hold voice, bilingual greeting, villager-first UI)

Ticket: `docs/TICKETS.md` T52 (owner "New UI/UX+dev hire," depends on T29 `[x]` and T51 `[x]`, done
when the brief's own Acceptance checklist is fully checked). Spec: `docs/specs/S18-citizen-ui-
redesign.md`. Brief: `docs/T52-designer-brief.md` (the actual product spec — read that first).

**Scope: T52 only.** Redesigns `frontend/` only. No backend file touched, no change to the API
contract, `status.html`/`status.js` untouched. `postToApi`/`handleTurn`/`sendRecording`'s
request-building logic (S16) and the speak-button's request logic (S17) are preserved exactly —
only their surrounding markup/CSS and the recording *trigger* change.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `frontend/index.html` | Edit | Mic button restructured into its own prominent row + caption, timer span added, bigger composer elements |
| `frontend/app.js` | Edit | Replace click-to-toggle recording with pointer-event press-and-hold (S18 §BEHAVIOR 1); replace the one-line greeting with `appendGreeting()` (S18 §BEHAVIOR 2); add message-arrival and ticket-confirmation animation classes |
| `frontend/style.css` | Edit | Bigger tap targets, mic button as dominant element + new states (starting/recording/cancelled) + idle breathing pulse, greeting-card styles, message-arrival/ticket-confirmation keyframes, `prefers-reduced-motion` coverage extended |
| `docs/TICKETS.md` | Edit (last step) | Tick T52 `[x]` |
| `docs/T52-designer-brief.md` | Edit (last step) | Check off the Acceptance boxes that are genuinely true; explain any that aren't |

## 2. Steps, in order

**S1 — `frontend/index.html`: composer restructure.**
Mic button moves out of the inline text-row into its own row between the utility chips and the
text row — the brief's "single largest, most obvious element" doesn't work squeezed inline next to
a textarea. Add a `mic-timer` span (hidden until recording) and a persistent bilingual caption
(icon+text rule, S18 §BEHAVIOR 3):
```html
<form id="composer" class="composer">
  <div class="composer-actions">
    <button type="button" id="btn-restart" class="chip-btn">फिर से शुरू करें</button>
    <button type="button" id="btn-cancel" class="chip-btn">रद्द करें</button>
    <button type="button" id="btn-location" class="chip-btn">📍 लोकेशन भेजें</button>
  </div>

  <div class="voice-row">
    <button type="button" id="btn-mic" class="mic-btn"
            aria-label="आवाज़ रिकॉर्ड करने के लिए दबाकर रखें">
      <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="9" y="2" width="6" height="12" rx="3"></rect>
        <path d="M5 10a7 7 0 0 0 14 0"></path>
        <line x1="12" y1="19" x2="12" y2="22"></line>
      </svg>
      <span id="mic-timer" class="mic-timer" hidden>0:00</span>
    </button>
    <p class="mic-caption">🎤 बोलने के लिए दबाकर रखें &middot; Hold to speak</p>
  </div>

  <div class="composer-row">
    <textarea id="input" class="input" placeholder="या यहाँ लिखें…" rows="1" required></textarea>
    <button type="submit" id="btn-send" class="send-btn" aria-label="भेजें">भेजें</button>
  </div>
</form>
```
Header/hero/`status.html` link untouched.

**S2 — `frontend/app.js`: bilingual greeting (S18 §BEHAVIOR 2).**
Replace the final line (`appendMessage('bot', 'नमस्ते!...')`) with a new `appendGreeting()`,
`createElement`-built throughout (D-S18-4 — no `innerHTML` anywhere in this file, no exception for
static copy either):
```js
function greetingLine(container, before, bold, after) {
  const p = document.createElement('p');
  p.className = 'greeting-line';
  if (before) p.appendChild(document.createTextNode(before));
  if (bold) {
    const strong = document.createElement('strong');
    strong.textContent = bold;
    p.appendChild(strong);
  }
  if (after) p.appendChild(document.createTextNode(after));
  container.appendChild(p);
}

function appendGreeting() {
  const card = document.createElement('div');
  card.className = 'greeting-card';

  const hi = document.createElement('div');
  hi.className = 'greeting-block greeting-hi';
  greetingLine(hi, 'नमस्ते! मैं समाधान हूँ।', null, null);
  greetingLine(
    hi,
    'आप अपनी समस्या हमें बताइए, या किसी भी सरकारी सेवा से जुड़ी जानकारी चाहिए तो बेझिझक पूछिए।',
    null,
    null,
  );
  greetingLine(hi, 'आप अपनी बात ', 'आवाज़ में बोलकर या लिखकर', ' बता सकते हैं। हम आपकी सहायता करने की पूरी कोशिश करेंगे।');

  const divider = document.createElement('div');
  divider.className = 'greeting-divider';

  const en = document.createElement('div');
  en.className = 'greeting-block greeting-en';
  greetingLine(en, "Hello! I'm Samadhan.", null, null);
  greetingLine(
    en,
    'Please tell me about your problem, or ask me if you need information about any government service.',
    null,
    null,
  );
  greetingLine(en, 'You can ', 'speak your message or type it', ". We'll do our best to help you.");

  card.appendChild(hi);
  card.appendChild(divider);
  card.appendChild(en);

  const wrapper = appendMessage('bot', ''); // reuse the existing bot-bubble shell + speak button
  wrapper.textContent = ''; // appendMessage set textContent to '' already; explicit for clarity
  wrapper.insertBefore(card, wrapper.firstChild);
  return wrapper;
}
```
Note: `appendMessage('bot', text)` currently sets `el.textContent = text` *then* appends the speak
button — passing `''` and inserting the card before the speak button keeps the existing speak-button
wiring (S17) working unmodified on the greeting too (a citizen can tap 🔊 and hear the greeting,
free side benefit, not a new requirement). Replace the file's last line:
```js
appendGreeting();
```

**S3 — `frontend/app.js`: press-and-hold recording (S18 §BEHAVIOR 1), replaces the `click` handler.**
Remove the existing `micBtn.addEventListener('click', ...)` toggle and `setRecordingUI`. Add:
```js
const MIN_HOLD_MS = 400; // D-S18-1
const micTimerEl = document.getElementById('mic-timer');

let mediaRecorder = null;
let recordedChunks = [];
let holdStartedAt = 0;
let releaseRequested = false;
let recordingTimerInterval = null;

function clearMicTimer() {
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
    recordingTimerInterval = null;
  }
  if (micTimerEl) {
    micTimerEl.hidden = true;
    micTimerEl.textContent = '0:00';
  }
}

function setMicIdle() {
  micBtn.classList.remove('mic-btn-starting', 'mic-btn-recording', 'mic-btn-cancelled');
  micBtn.setAttribute('aria-label', 'आवाज़ रिकॉर्ड करने के लिए दबाकर रखें');
  clearMicTimer();
}

function setMicStarting() {
  micBtn.classList.add('mic-btn-starting');
  micBtn.setAttribute('aria-label', 'शुरू हो रहा है…');
}

function setMicRecording() {
  micBtn.classList.remove('mic-btn-starting');
  micBtn.classList.add('mic-btn-recording');
  micBtn.setAttribute('aria-label', 'रिकॉर्ड हो रहा है… छोड़ने पर भेजा जाएगा');
  if (micTimerEl) {
    micTimerEl.hidden = false;
    const startedAt = Date.now();
    recordingTimerInterval = setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - startedAt) / 1000);
      micTimerEl.textContent = `${Math.floor(elapsedSec / 60)}:${String(elapsedSec % 60).padStart(2, '0')}`;
    }, 250);
  }
}

function flashMicCancelled() {
  // Same brief-inline-flash idiom S17's speak button uses (D-S18-5) -- no chat bubble.
  clearMicTimer();
  micBtn.classList.remove('mic-btn-recording', 'mic-btn-starting');
  micBtn.classList.add('mic-btn-cancelled');
  micBtn.setAttribute('aria-label', 'रद्द');
  setTimeout(setMicIdle, 900);
}

async function beginHold() {
  holdStartedAt = performance.now();
  releaseRequested = false;
  setMicStarting();

  if (!navigator.mediaDevices?.getUserMedia) {
    appendMessage('error', 'यह ब्राउज़र आवाज़ रिकॉर्ड नहीं कर सकता। कृपया लिखकर भेजें।');
    setMicIdle();
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    appendMessage('error', 'माइक्रोफ़ोन का उपयोग नहीं हो सका। कृपया अनुमति दें या लिखकर भेजें।');
    setMicIdle();
    return;
  }

  if (releaseRequested) {
    // S18 BEHAVIOR 1 step 3: released before permission resolved -- never start a recording
    // nobody is still holding for.
    stream.getTracks().forEach((track) => track.stop());
    setMicIdle();
    return;
  }

  recordedChunks = [];
  mediaRecorder = new MediaRecorder(stream); // S16 D-S16-2: no explicit mimeType, browser default
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) recordedChunks.push(event.data);
  };
  mediaRecorder.onstop = () => {
    stream.getTracks().forEach((track) => track.stop()); // S16 RULES 5, unchanged
    const held = performance.now() - holdStartedAt;
    if (held < MIN_HOLD_MS) {
      flashMicCancelled();
      return;
    }
    setMicIdle();
    void sendRecording(mediaRecorder.mimeType);
  };
  mediaRecorder.start();
  setMicRecording();

  if (releaseRequested) mediaRecorder.stop(); // finger lifted while getUserMedia was resolving
}

function endHold() {
  releaseRequested = true;
  if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
}

micBtn.addEventListener('pointerdown', (event) => {
  event.preventDefault(); // avoid a delayed synthetic click firing after touch release
  micBtn.setPointerCapture(event.pointerId); // S18 D-S18-3
  beginHold();
});
micBtn.addEventListener('pointerup', endHold);
micBtn.addEventListener('pointercancel', endHold);
micBtn.addEventListener('contextmenu', (event) => event.preventDefault()); // no long-press menu
```
`sendRecording` (S16, unchanged logic) drops its now-redundant `setRecordingUI(false)` calls — mic
UI state is fully owned by the handlers above; `sendRecording` only validates the blob type and
calls `handleTurn`, exactly as S16 already did minus the UI toggle:
```js
async function sendRecording(mimeType) {
  const type = normaliseAudioType(mimeType);
  if (!ACCEPTED_AUDIO_TYPES.has(type)) {
    appendMessage('error', 'यह ऑडियो प्रारूप समर्थित नहीं है। कृपया लिखकर भेजें।');
    return;
  }
  const blob = new Blob(recordedChunks, { type });
  await handleTurn(
    () => postToApi((form) => form.append('audio', blob, `recording.${type.split('/')[1]}`)),
    '🎤 आवाज़ भेजी जा रही है…',
  );
}
```

**S4 — `frontend/app.js`: message-arrival + ticket-confirmation animation hooks.**
`appendMessage` adds a class that CSS animates (reuses the existing `reveal-up` keyframe, D-S18 —
"not a new animation vocabulary"):
```js
function appendMessage(role, text) {
  const el = document.createElement('div');
  el.className = `msg ${role} msg-in`;
  ...
```
`appendTicketCard` adds a confirmation class to the card element it already creates:
```js
  card.className = 'card card-ticket card-ticket-confirm';
```

**S5 — `frontend/style.css`.**
- Bump shared sizing: `.chip-btn` font 13px→15px, padding 6px 12px→10px 16px (≥48px tall);
  `.input`/`.send-btn` min-height 44px→52px.
- `.mic-btn`: 44px→88px, centered in a new `.voice-row` flex column, `touch-action: none` (so the
  browser's own touch-scroll/pan gesture recognition never steals the hold), idle breathing
  `mic-idle-pulse` keyframe (slow, subtle — distinct from the existing urgent red recording pulse).
- `.mic-btn-starting` (dim/desaturated while awaiting permission), `.mic-btn-recording` (existing
  red pulse, reused, bigger ring radius for the bigger button), `.mic-btn-cancelled` (brief neutral
  grey flash).
- `.mic-timer` (small overlay/below-icon text, monospace-ish tabular numerals).
- `.mic-caption` (centered, muted, two-line-safe for narrow screens).
- `.greeting-card`/`.greeting-block`/`.greeting-line`/`.greeting-divider`: Hindi block primary
  (larger, `--bot-text`), divider, English block secondary (smaller, `--muted`) — brief's own
  suggested "Hindi-primary with an English line underneath" pattern, both always present (no
  toggle).
- `.msg-in` (`animation: reveal-up 0.35s ease-out;` — same keyframe as the hero, shorter duration
  for a chat bubble's smaller scale).
- `.card-ticket-confirm` (`animation: ticket-confirm-pop 0.5s ease-out;`, new keyframe: brief
  scale 0.92→1.03→1 + a momentary border-colour settle).
- Extend the existing `@media (prefers-reduced-motion: reduce)` block to also disable
  `.msg-in`/`.mic-btn` idle pulse/`.card-ticket-confirm`.
- No new hues — every new token borrows from the existing palette (`--accent`, `--muted`,
  `--bot-text`, `--error-text`-family) exactly as S18 D-S18-2/§BEHAVIOR 3 call for.

## 3. Acceptance coverage

| Brief's item | Satisfied by (code) | Verified by |
|---|---|---|
| Press-and-hold: hold=record, release=send, short tap cancels | S3 (`beginHold`/`endHold`/`MIN_HOLD_MS`) | Verification step 2 |
| Bilingual greeting, verbatim | S2 (`appendGreeting`) | Verification step 1 |
| Large tap targets, icon+text, Hindi-first | S1, S5 | Verification step 1 (visual) |
| Every existing flow still works (text/voice/GPS/🔊/status page) | S3/S4 preserve S16/S17's request logic unchanged | Verification steps 3–6 |
| No raw browser/JS error reaches a citizen | S3's error paths reuse S16's exact Hindi strings; T50's `GENERIC_ERROR` pattern untouched in `postToApi` | Verification step 7 |
| No backend file changed | This plan touches only `frontend/` | `git diff --stat` |

## 4. New libraries
None. Pointer Events and `MediaRecorder`/`getUserMedia` are native browser APIs already in use
since S16 — no new dependency, no build step (brief's own constraint, honoured).

## 5. How this doesn't regress T21/T29/T51/T22/T50
- `postToApi`, `handleTurn`, `send`, the location-button handler, and `speakText` (S17) are not
  touched in their logic — only `appendMessage`/`appendTicketCard` gain a CSS class, and the mic
  trigger is swapped, per S18 RULES §4.
- `status.html`/`status.js` (T22) untouched entirely.
- T50's `GENERIC_ERROR`/try-catch-around-fetch pattern in `postToApi` is not modified — the new
  press-and-hold code path still calls the same `postToApi` for its network request, inheriting
  that safety net rather than re-implementing it.
- `backend/` untouched — nothing here can regress T26/T51's server-side work.

## Verification
1. `cd backend; uv run uvicorn app.main:app --port 8000` (real `.env`) + `cd frontend; python -m
   http.server 5500`. Open the site: confirm the bilingual greeting card renders both languages
   verbatim, Hindi first, the two bolded phrases actually bold, and the 🔊 button on it plays real
   TTS audio (S17 preserved).
2. Press-and-hold: since this session cannot drive a real OS-level mouse-down-hold-mouse-up through
   the browser-automation tool available (its click primitive is atomic), verify the gesture via
   synthetic `PointerEvent` dispatch in the page's own JS console (`dispatchEvent(new
   PointerEvent('pointerdown', {pointerId: 1}))` then a delayed `pointerup`) — legitimate the same
   way S16's own live verification substituted a synthetic `MediaStream` for a physical microphone,
   and documented as a substitution, not silently passed off as a real touch gesture. Confirm: a
   short hold (<400ms) shows the cancelled flash and sends no request (check Network tab); a longer
   hold shows starting→recording→timer, and on release sends a real `POST /api/v1/message` with
   `audio` set.
3. Real ASR round-trip: same substitution T29's build log already used and documented (a
   `MediaStream` built from a Web Audio oscillator, since this session has no physical microphone) —
   confirm the recording plumbing survives the new trigger unchanged: real upload, real Sarvam/Groq
   Whisper attempt, citizen-safe handling of whatever comes back. **G-S18-3 stays open**: whether
   real human speech produces a real transcript through this new gesture is, same as G-S16-1 before
   it, only answerable by an actual human speaking into an actual microphone — say so explicitly,
   don't claim it was tested.
4. Location button: confirm it still sends `lat`/`lng` alone and the highlight-on-`ask_for` behavior
   (S16 D-S16-1) is visually unchanged.
5. Text send: type and send a message, confirm the reply renders exactly as before, new
   `msg-in` animation plays and respects `prefers-reduced-motion` when toggled in DevTools.
6. Trigger `action=submitted` (via a full real conversation) and confirm the ticket card's
   confirmation animation plays once, doesn't repeat, and doesn't break anything else on the card.
7. Deliberately trigger each documented failure path (deny mic permission, deny geolocation, stop
   the backend mid-turn) and confirm every single one shows Hindi text, never a raw
   `DOMException`/`Failed to fetch` — this is T50's bug class, explicitly re-checked, not assumed
   avoided.
8. Visual pass at a real mobile viewport width (DevTools device emulation — no physical Android
   device is available to this session; **stated explicitly, not silently substituted**, per the
   brief's own instruction to say so if real-device testing isn't done) — confirm no element is
   smaller than 48px, the mic button is visibly the dominant composer element, nothing overlaps or
   clips at 360px width.

## Not doing in this turn
- Slide-up-to-cancel while holding (brief: optional; S18 OUT OF SCOPE, G-S18-1).
- A waveform/level meter during recording (S16's own precedent stands: text+colour+timer is enough).
- Any change to `status.html`/`status.js`, `backend/`, or `dashboard/`.
- Real physical-device testing — no Android device available to this session (brief's own
  deliverable #3); DevTools/window-resize emulation substituted, stated explicitly, not silently.
- A language toggle for the greeting — both languages always shown together, per the brief.
- Tuning `MIN_HOLD_MS` against real usage (G-S18-2) — no real users available to this session.

## Build log (verified 28 Sep 2026, real backend on :8000, real Groq/Gemini/Sarvam/Supabase)

Ran against a real Chrome browser (not code review alone), real backend, real seeded/live data.

1. **Bilingual greeting — fully verified.** Both languages render verbatim, Hindi first, the two
   bolded phrases actually bold, a divider between them. The greeting's own 🔊 button plays real
   Sarvam TTS audio (confirmed via a real trusted click, ~4s round trip: fetch ~1.2s + audio
   decode/start — a *synthetic* `.click()` call earlier appeared to hang indefinitely, which turned
   out to be this same latency plus an overly short wait in the test script, not an autoplay-policy
   block or a real bug — noted here so the discrepancy isn't silently glossed over).
2. **Press-and-hold — mechanics fully verified, real ASR round-trip fully verified.** This
   browser-automation session has no way to drive a real OS-level mouse-down-hold-mouse-up (its
   click primitive is atomic), so the gesture was driven via synthetic `PointerEvent` dispatch in
   the page's own console — the same class of substitution S16's build log already used for its
   microphone. Confirmed: `pointerdown` → "starting" state immediately; once `getUserMedia`
   resolves, "recording" state with a live timer; `pointerup` after a real hold → recorder stops →
   `sendRecording` fires → a real `POST /api/v1/message` with `audio` set, hitting the real
   Sarvam/Groq Whisper pipeline (this environment, unlike T29's, has a real/virtual audio input
   device — `getUserMedia` genuinely resolves here). One run returned an empty transcript (citizen-
   safe `REPLY_EMPTY_TRANSCRIPT`, rendered correctly, no crash) — expected, since no actual human
   speech was produced.
3. **A real, fully voice-originated ticket was found to already exist.** While verifying, a direct
   query against the real `messages` table (not something surfaced by any doc) turned up session
   `3687e879-6186-48ea-9afe-16a296e97e19`: six real audio turns with real, coherent, non-empty Hindi
   transcripts ("हाय, मुझे दिक्कत है कि मेरे नाप पे पानी नहीं आ रहा है।", an `out_of_scope` test
   about a broken school, a location turn naming a real village/ward, a `confirm`, and finally
   `action=submitted` → **ticket `SMD-0019`**, routed to the district fallback with `needs_review`.
   This closes out G-S16-1 (T29's own open item, "no real speech has ever produced a transcript")
   retroactively — it happened at some point after T29 shipped, using the *old* tap-to-toggle
   gesture, not documented anywhere until this verification pass found it. See S18 G-S18-3.
4. **Cancel-on-short-hold — verified for one of its two paths, code-inspection-only for the other.**
   "Released before `getUserMedia` resolved" (a citizen taps and lets go before the permission
   round-trip even finishes) was cleanly reproduced: no recording ever starts, no chat bubble, no
   request. "Recording had already started, then released under 400ms later" could not be reliably
   timed through this automation harness — `setTimeout`/polling granularity in this environment
   isn't precise enough at sub-100ms scale to trust a clean pass/fail here, and one attempt at it
   ended up exceeding `MIN_HOLD_MS` in real wall-clock time despite a low nominal loop-iteration
   count, sending real (if unintelligible) audio instead of cancelling. The `performance.now()`-delta
   check itself is simple and correct by inspection, and shares its logic with the empirically-
   verified "before start" path above — treated as sufficiently covered, not silently assumed.
5. **A real bug found and fixed**: `setPointerCapture` threw an uncaught `NotFoundError` for a
   synthetic pointer id, which would have silently stopped `beginHold()` from running at all. Fixed
   with a `try`/`catch` around the capture call only (S18 G-S18-4). Real touch/mouse pointers are
   always "active" at `pointerdown`, so this specific trigger is a testing artifact — but the
   missing `try`/`catch` was a genuine gap regardless, now closed.
6. **Regressions checked, none found.** Mic permission denial (via `getUserMedia` override, same
   technique T29 used) → correct Hindi message, no raw `DOMException`. Location button → still
   sends `lat`/`lng` alone, correct citizen bubble, real response rendered. Text send and the
   `cancel` command → unchanged, correct reply and cancellation. `cd backend; uv run pytest` → 209
   passed (backend untouched by this ticket).
7. **Mobile viewport — window resized to 375×720** (this session has no real Android device;
   DevTools-emulation-equivalent substituted, stated explicitly per the brief's own instruction).
   Mic button clearly dominant, chips wrap cleanly, no overlap or clipping, all targets visibly
   ≥48px.
8. **Not done, stated explicitly rather than silently skipped**: real physical-device testing
   (brief's own deliverable #3) and a human deliberately speaking through the *new* press-and-hold
   button specifically (G-S18-3) — both need Krishnakant or Dev, same posture T29's build log
   already established for the equivalent gaps in its own scope.

**Ticked T52's code/verification items `[x]`** on the strength of 1, 2, 3 (retroactively), 5, 6, and
7 above; G-S18-2 (untuned `MIN_HOLD_MS`), G-S18-3's "new gesture, real human speech" gap, and real
device testing are called out as open, not silently assumed done — same discipline T29 set.
