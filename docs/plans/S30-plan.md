# Plan: S30 — greeting voice on first touch (Hindi + English), early mic permission, backend warm-up

Spec: `docs/specs/S30-greeting-voice-first-touch.md`. Scope: only what the spec lists. The API contract changes additively (`language`).

## Files
| Path | Action |
|---|---|
| `backend/app/tts.py` | `synthesize(text, language="hi")` -> `hi-IN` / `en-IN` |
| `backend/app/schemas.py` | `SpeakRequest.language: Literal["hi","en"] = "hi"` |
| `backend/app/routes.py` | pass `body.language` |
| `backend/tests/test_tts.py`, `test_routes.py` | tests for default, `en`, invalid value |
| `frontend/app.js`, `frontend/widget.js` | speech helper takes a language; greeting playback state machine; first-touch handler (greeting + mic priming); warm-up ping |
| `docs/specs/S17-text-to-speech.md` | one line noting the optional `language` |

## Steps
1. **Backend language option** (5 min): edit the three files, add tests, run pytest and ruff. Restart the local backend.
2. **Frontend helper**: `fetchSpeech(text, lang)` calling `/speak` with `{text, language}`; `fetchHindiAudio(text)` stays as a thin wrapper so nothing else changes.
3. **Greeting playback**: one shared `greetingAudio` element; state `idle -> playing -> done`; `playGreetingVoice()` plays Hindi, waits for `ended`, plays English; guarded so it can never run twice.
4. **First-touch handler** (registered at load, fires once): synchronously unlocks `greetingAudio` (silent sound), starts `playGreetingVoice()` if the greeting text is on screen (else marks `touched` so it starts when the greeting appears), then `primeMicPermission()`.
5. **Greeting card**: remove the failing 3-second autoplay attempt (D-S30-3); "Tap to listen" visible from the start, hidden once the voice starts.
6. **Warm-up ping** at load.
7. Same in `widget.js` (S19 D-S19-2).
8. **Verify**: backend tests; in Chrome against the local site and then the deployed one: state machine, single playback, button visibility, stubbed mic API (asks only on `prompt`, releases tracks, never on the mic button), ping; the real-phone check is the Lead's.
9. Update the spec's acceptance boxes and a build log.

## Undo / come back to this step
Only these files change and all are clean at the current commit, so the whole change is undone with one command:
`git checkout -- backend/app/tts.py backend/app/schemas.py backend/app/routes.py backend/tests/test_tts.py backend/tests/test_routes.py frontend/app.js frontend/widget.js docs/specs/S17-text-to-speech.md`
(then delete `docs/specs/S30-*.md` and this plan if abandoning). Nothing is committed until the Lead says so; if committed, `git revert <commit>` undoes it.

## Risks
- iPhone Safari: greeting should work (unlock trick); voice-note replies may still be blocked. Unverified without a device.
- Two TTS calls per touched page view (Groq is the LLM limit; Sarvam TTS has its own limits, unchecked).
- Denying the mic is permanent until the visitor changes site settings (known trade-off, S30 §2.4).
