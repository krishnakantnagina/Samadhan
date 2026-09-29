# S30 — Greeting voice on the first touch (Hindi then English), mic permission asked early, backend woken on load
Implements: `backend/app/tts.py`, `backend/app/schemas.py` (`SpeakRequest.language`), `backend/app/routes.py`, frontend `app.js` and
`widget.js` · Depends on: S17 (text-to-speech), S18 (greeting), S19 (widget parity), S22 (deploy) · Version: v1 · Status: Approved by the Lead (30 Sep), built

## 1. Problem (seen on the deployed site)
- The greeting *voice* often does not play: browsers refuse sound that starts before the visitor has touched the page. Today the page tries
  once at 3 seconds, fails silently, and shows a "Tap to listen" button that many visitors never notice.
- The greeting is spoken in **Hindi only**; the English half is text only (S18 D-S18, "muted"). The Lead now wants both spoken.
- The first press-and-hold of the mic triggers the browser's permission box in the middle of the hold, so the first recording can fail.
- On the free Render host the backend may be asleep, so the first voice request takes up to a minute.

## 2. Behaviour
1. **First touch plays the greeting.** The first tap, click, key press or scroll-touch anywhere on the page starts the greeting voice:
   **Hindi first, then English**, one after the other (two Sarvam calls). Desktop and phone. If the visitor already touched the page before the greeting
   text appeared, playback starts as soon as it appears.
2. **Same tap unlocks sound** (needed on iPhone Safari): the tap synchronously starts a shared audio element with a silent sound, and the
   greeting audio is then played on that same element. Voice-note replies keep their own elements (unchanged); iPhone behaviour for those is **not verified**.
3. **"Tap to listen" stays visible** under the greeting from the moment it appears until the voice has started, as the fallback for anyone who
   does not touch anything. Tapping it plays Hindi then English too. It never starts a second playback while one is running.
4. **Mic permission is asked once, on that first touch**, not on page load: the page triggers the browser's own prompt and releases the mic
   immediately (no recording, no indicator left on). It first reads the permission state and does nothing if it is already granted or denied. It is
   skipped when the browser cannot report the state (Safari), when there is no mic API, and when the touch was on the mic button itself
   (that press handles its own permission). A denial is never an error: the existing Hindi message and typing still work.
5. **The backend is woken on page load** with one quiet `GET /health`; failure is ignored.
6. **English voice.** `POST /api/v1/speak` gets an optional `language` (`"hi"` default, `"en"`), mapped to Sarvam `hi-IN` / `en-IN` (checked live:
   `bulbul:v3` with the same speaker answers `en-IN` with valid audio). Omitting it keeps today's behaviour exactly; any other value is rejected as invalid input.
7. No welcome screen, no popup of our own. Location permission is not asked here (it stays on the yes/no chips).

## 3. Never breaks the page
Every browser call (`play`, `getUserMedia`, `permissions.query`, `fetch`) is inside try/catch and collapses to "do nothing" or the existing
citizen-safe message (T50). If the greeting audio fails, the text greeting and the button remain.

## 4. Out of scope
- Making voice-note replies play on iPhone Safari if it blocks them (needs a shared unlocked element for all replies; a larger change).
- Asking for location permission early; a custom welcome screen.

## ACCEPTANCE
- [x] `language` accepted as `hi` (default) and `en`; anything else is a 400; the default request still sends `hi-IN` (unit tests)
- [x] First touch starts Hindi then English on the shared element; a second touch or the button never starts a second playback (browser check)
- [x] "Tap to listen" is visible until the voice starts (browser check)
- [x] Mic priming: asks only when the state is `prompt`, releases the stream, never on the mic button, never re-asks (browser check with a stubbed API)
- [x] `/health` ping on load, failure silent (browser check)
- [x] Same in `widget.js`
- [x] All suites and ruff pass; nothing is committed without the Lead's say-so
- [ ] **Needs the Lead on a real phone (and ideally an iPhone):** the greeting voice after a touch, the mic prompt once, Hindi then English, no double playback

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S30-1 | First touch, not a popup or welcome screen | Lead's idea: ask for the mic directly; the touch is also what unlocks sound |
| D-S30-2 | One shared audio element for the greeting, unlocked by a silent sound in the tap | Works on iPhone Safari, which only allows a play() that started in a tap |
| D-S30-3 | Do not prefetch the greeting audio on load | Two Sarvam calls per page view even for visitors who never touch it would waste the quota |
| D-S30-4 | `language` is optional and defaults to Hindi | No contract break: every existing caller is unchanged |
| D-S30-5 | Skip mic priming when the state cannot be read | Safari would ask again on every visit, which is worse than asking at the first hold |

## BUILD LOG (30 Sep 2026)
Backend 418 pytest passed (3 new + 2 older tests adjusted to accept the new argument), ruff clean. **Live (Sarvam):** `hi`, `en`, and no language all
return audio; `fr` returns a clean 400. **Browser (Chrome, local site, with stubbed audio and permission APIs, because a script cannot make a real tap or
show a real mic prompt):** a touch made BEFORE the greeting text appeared gave, in order: silent unlock, permission read, mic prompt once, mic released,
`speak hi`, `speak en`, Hindi plays, English plays, state `done`, "Tap to listen" hidden; a second touch and the button started nothing new. A first touch ON the mic button
did not ask for the mic; an already-granted permission did not ask; with `/speak` failing there was no error bubble, the text greeting stayed and the button
stayed visible to retry; the `/health` ping happened at load. Same result in the widget on the status page (English follows Hindi after the second fetch).
**Not verified (needs a real phone, ideally an iPhone too):** that real taps unlock real sound on Android Chrome and iPhone Safari, the real mic prompt appearing once, the audible
Hindi-then-English greeting, and that voice-note replies still play on iPhone. **Undo:** `git checkout -- backend/app/tts.py backend/app/schemas.py backend/app/routes.py backend/tests/test_tts.py backend/tests/test_routes.py frontend/app.js frontend/widget.js`.
