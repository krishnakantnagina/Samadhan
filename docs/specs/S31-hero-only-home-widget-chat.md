# S31 — Home page is the hero only; the chat is the widget, opened from the mic button; greeting plays a pre-recorded file
Implements: `frontend/index.html`, `frontend/widget.js`, `frontend/style.css`, `frontend/greeting-hi.wav` (new asset) ·
Depends on: S19 (widget), S18 (greeting), S17 (TTS), S29 (status link) · Version: v1 · Status: **Draft, waiting for Lead approval**
(nothing is built, committed or pushed until the Lead says go)

## 1. Problem
`index.html` is two screens: the hero, then a full chat page below it (`#app`, driven by `app.js`). The Lead wants a better first
impression: the hero stays as the only page, and the chat opens as the floating widget from the hero's "Start Conversation" mic.
Second problem: the greeting audio is fetched from Sarvam TTS on every load and starts with no user click, so browsers block it
(the "Listen" fallback button shows) and every visit spends TTS quota. Sarvam TTS currently answers 400 as well.

## 2. Decisions
| # | Decision |
|---|---|
| D-S31-1 | The hero looks exactly as it does today (title, tagline, description, mic animation, preview card). Only the ↓ scroll cue is removed, because nothing is below it (Lead to confirm, section 8). |
| D-S31-2 | The full chat page is **hidden, not deleted**: `<div id="app" hidden>` stays in `index.html`, and `app.js` stays in the repo. |
| D-S31-3 | `app.js` is **not loaded** on the page. Loaded, it would auto-scroll to the hidden block, run its own greeting and share the session id with the widget. |
| D-S31-4 | The widget is the only chat. It is loaded on `index.html` the same way `status.html` already loads it. |
| D-S31-5 | The greeting audio is a static file, `greeting-hi.wav`, played with `new Audio()`. No `/speak` call for the greeting. Reply speak buttons still use TTS (their text changes). |
| D-S31-6 | No backend change. |

## 3. Behaviour
1. Page load: only the hero shows. The widget's small floating button and its "सहायता चाहिए?" label are **hidden on this page**
   (the hero mic is the entry point, two entry points on one screen would confuse a first-time user). They stay on `status.html`.
2. Click on the hero mic (`#hero-cta`) or its "Start Conversation" text: the widget panel opens (same 220 ms animation) and the input
   gets focus. The hero mic keeps its animation.
3. On first open of the page load: typing indicator for 3 s, then the bilingual greeting card renders and `greeting-hi.wav` plays.
   The open click is a user gesture, so playback is allowed. If `play()` is still rejected, the existing "Listen" button shows.
4. Close (× in the panel) and reopen: same conversation, no second greeting. The floating button appears after the first open so a
   citizen who closed the panel can reopen it (on this page it is hidden only until the first open).
5. Session id: same `samadhan_session_id` key as today. A citizen coming back from `status.html` continues the same conversation.
6. The status link "अपनी शिकायत की स्थिति जानें" moves from the hidden chat header into the hero (below the CTA row), styled as a
   quiet text link. The bot's own status replies (S29) point to it, so it must stay visible.
7. Phone (≤ 480 px): panel is full-screen (100% width and height, respecting `env(safe-area-inset-*)`), not the 400 × 620 card.
   Desktop: the panel is a little larger on the home page (about 420 × 680) but stays anchored bottom-right.
8. No auto-scroll, no auto-open (the citizen chooses to start; a page that opens a chat by itself also blocks audio anyway).

## 4. File-by-file changes
### `frontend/index.html`
- Remove `<div class="hero-scroll-cue">`.
- Wrap the existing chat block in `<div id="app" class="app-shell" hidden>` and add a comment: disabled on purpose, see S31,
  re-enable by removing `hidden` and re-adding the `app.js` script tag.
- Replace `<script src="app.js">` with `<script src="widget.js">` (after `config.js`).
- Add the status link under `.hero-cta-row`.

### `frontend/widget.js`
- Export one small hook on `window.SamadhanWidget = { open() {…} }` (calls `setOpen(true)`). Purely additive, no host coupling.
- Hero wiring lives in `widget.js` itself: if `#hero-cta` exists, its click calls `setOpen(true)`. (`status.html` has none, so
  nothing changes there.) A page attribute `data-hero` on `<body>` hides the floating button until first open (behaviour 1, 4).
- `playGreetingAudio()`: `new Audio('greeting-hi.wav').play()` instead of `fetchHindiAudio(spokenHi)`. Keep the Listen fallback.
- The greeting text stays as it is (already matches S29's general wording).
- No change to `postToApi`, `send`, mic, location, cards, commands.

### `frontend/style.css`
- `body[data-hero] #samadhan-widget-toggle, body[data-hero] #samadhan-widget-label { display: none }` until `.samadhan-widget-seen`.
- Larger panel on hero page, full-screen panel at ≤ 480 px. The `prefers-reduced-motion` rules stay.
- `.hero-status-link` style. Remove nothing else (the `.app-*` styles stay for the hidden block).

### `frontend/greeting-hi.wav` (asset, exists, untracked)
- 15.0 s, mono, 44.1 kHz, 16-bit, 1.3 MB. Too heavy on village mobile data. Options: (a) convert to mono MP3 about 64 kbps (about 120 KB),
  needs ffmpeg, which is **not installed** on this machine; (b) downsample the WAV to 16 kHz mono with Python (about 480 KB);
  (c) ship as is. Recommendation: (a) if the Lead can install ffmpeg or converts it, else (b).
- The file must be checked by ear against the greeting text (`spokenHi` in `widget.js`) before it ships.

### Other
- `README.md` folder table: `index.html` is the hero + widget, `app.js` is kept but unused.
- `docs/TICKETS.md`: add a line under T52/T53 for this change.

## 5. Rules
1. Never `innerHTML` on network-derived text (unchanged rule for the whole frontend).
2. The API base, error texts and session key stay identical to today.
3. `app.js` and the hidden `#app` are not edited in this change, so turning them back on is a two-line revert.
4. No new library, no build step (project rule).

## 6. Risks and how they are handled
| Risk | Handling |
|---|---|
| Hidden code goes stale when the widget changes | Comment in `index.html`; `app.js` header comment says "unused since S31". |
| Full-screen panel on phones hides the hero mic | Intended; the × returns to the hero. |
| Audio still blocked (iOS Safari, low-power mode) | "Listen" button fallback stays. |
| Recording says different words than the card | Ear-check before ship; the card text is the source of truth. |
| Two entry points confuse | Floating button hidden until first open on the home page. |

## 7. Tests (manual, no test framework exists for the frontend)
1. Home: only the hero shows, no scroll, no ↓, no floating button.
2. Click the hero mic: panel opens, typing dots 3 s, greeting card, the recorded voice plays (Chrome desktop, Chrome Android).
3. Send a text message: the widget reaches the backend (network tab shows one `/message`, no `/speak` for the greeting).
4. Close, reopen: no second greeting, conversation kept. Reload: new greeting.
5. Press-and-hold mic, location button, restart, cancel, speak button on a reply (speak may fail while Sarvam TTS 400 stays open).
6. `status.html`: widget unchanged (button and label visible, greeting works, now with the recorded file).
7. 360 px wide phone view: panel full-screen, keyboard does not cover the input.
8. Backend down: the Hindi error text shows, no raw error.
9. `node --check frontend/*.js` passes.

## 8. Open questions for the Lead
1. Remove the ↓ scroll cue? (Recommended: yes.)
2. Audio size option (a), (b) or (c)? Is the recording by a generated voice or a human? Please confirm it says the same words as the card.
3. Hide the floating button on the home page until the first open (recommended), or always show it?
4. Do it before the 30 Sep noon submission, or leave for after the event?
5. Should this ride on `main` directly, or a branch first? (Nothing is committed or pushed without your word.)

## 9. Not covered
The Hindi `out_of_scope` misrouting and the Sarvam TTS 400 (both found in the 30 Sep live test) are separate problems. S31 does not fix
them, though it removes the greeting's dependence on TTS.
