# S23 — Location choice ("are you where the problem is?")
Implements: frontend `app.js` + `widget.js`, `specs/water_supply.yaml` question text, one validator guard ·
Depends on: S01 (`ask_for`), S03/S07 (location field, validator), S16 (location button), S17 (voice notes),
S19 (widget parity) · Feeds: S24 (map: more real GPS means more exact pins) · Version: v1 · Status: Draft

## 1. Why
Only 2 of 20 tickets have GPS, so the officer map (S24) had almost nothing exact to pin. Citizens rarely tap
the small "share location" chip. The Lead's requested flow asks it as a conversation:

> Bot: "Are you at the place where the problem is?"
> Yes → "Please share your current location" → GPS is sent.
> No ("I'm at home, the problem is near the water tank in my village") → "Please tell me the village name" → place name collected.

## 2. Constraint
**Backend GPS/routing behaviour does not change** (S09, S10, jurisdiction resolver, ticket creation untouched).
The flow is a *presentation* over the existing contract: GPS still arrives as `lat`+`lng` (S01 §4.1), a place as
`text`. The only backend-adjacent edits are the wording of the location question (spec YAML, which S03 says is the
source of question text) and one validator guard (§5).

## 3. Behaviour
1. When any bot reply has `ask_for == "location"`, its question is the new yes/no wording (YAML) and two quick-reply
   chips appear under that bubble: **"📍 हाँ, मैं यहीं हूँ"** and **"✍️ नहीं, मैं नाम बताऊँगा"**.
2. **Yes** → chips removed, the browser's `getCurrentPosition` is requested (same options and same failure messages as
   the S16 location button), and on success `lat`/`lng` are sent as a location turn (`📍 लोकेशन साझा की गई`).
3. **No** → chips removed, a local bot bubble (voice note, auto-plays: the tap was a gesture) says
   "ठीक है। कृपया अपने गाँव, मोहल्ले या वार्ड का नाम बताइए (बोलकर या लिखकर)।" and the text box is focused. The next
   message is an ordinary turn (place name → S09 fuzzy match).
4. **Typed or spoken yes/no instead of tapping.** While the last reply asked for location:
   - a typed whole-utterance yes/no (S20-style normalisation) is answered locally like the chip, **not sent**;
   - a voice message whose *transcript* is a yes/no is handled the same after the response arrives, and the backend's
     re-ask bubble for that turn is not shown.
   YES: `हाँ, हां, हा, जी, जी हाँ, जी हां, yes, y, ok, okay, ठीक है, हाँ मैं यहीं हूँ, हां मैं यहीं हूं, यहीं हूँ, यहीं हूं`.
   NO: `नहीं, नही, ना, जी नहीं, no, n, नहीं मैं यहाँ नहीं हूँ, मैं यहाँ नहीं हूँ, घर पर हूँ, मैं घर पर हूँ`.
5. The chips exist only on the **latest** bot reply that asks for location. Any other turn (restart, cancel, a place
   typed directly, an answer that moves on) clears the state. The existing "📍 लोकेशन भेजें" chip stays.
6. Failures never leak a raw error (T50): geolocation denied/timeout → the existing Hindi message asking for the ward.
7. Identical behaviour in `widget.js` (S19 D-S19-2).

## 4. Wording (spec YAML, `location.question`)
- hi: `क्या आप अभी उसी जगह पर हैं जहाँ पानी की समस्या है? अगर हाँ, तो "हाँ, मैं यहीं हूँ" दबाइए। अगर नहीं, तो अपने गाँव या वार्ड का नाम बताइए।`
- en: `Are you at the place where the water problem is? If yes, tap "Yes, I am here". If not, tell me your village or ward name.`
The mock API keeps its own canned text (contract examples unchanged).

## 5. Validator guard (needed for voice)
A spoken "हाँ" is transcribed and sent to the Turn Engine, whose only visible question was the location one. It could
return `location: "हाँ"`, which S07 would accept (2+ chars), and the citizen would jump to confirmation with a fake place.
`validator._validate_field` (location case) therefore rejects a value that is only a yes/no word (the YES/NO sets above,
lower-cased, punctuation stripped). Deterministic, tested, no other behaviour change. The Turn Engine prompt gets the
same one-line rule as belt and braces.

## 5b. Required backend fix found while verifying this flow (29 Sep)
`sessions.service_id` was never written: `SessionUpdate`/`save_turn` (S06) had no such field, so it stayed `NULL` forever.
A GPS-only turn (the "Yes" answer) skips the LLM (S05 D-S05-1) and returns `service_id = session.service_id = None`, which
the validator (S07 `apply`, first branch) treats as "no matching service" and answers `out_of_scope`, discarding an
otherwise complete complaint. Text turns hid this because the LLM re-derives the service every time. This is the
"unless required" exception: without it the requested flow cannot work.
Fix (small, no contract change): `SessionUpdate` gains `service_id`; `save_turn` writes it; `routes.py` passes the
validated `result.service_id` on ask/confirm/out_of_scope turns (unchanged session value when the LLM matched nothing),
`None` after submit/cancel/restart, and the existing value on an empty-transcript turn. Jurisdiction and ticket
creation code are not touched.

## 6. Out of scope
- Storing "was the citizen at the site" (no new column, no contract change).
- The generic-word location guard ("गाँव", "हैंडपंप": S21 OPEN), a separate decision.
- Any change to jurisdiction or routing.

## ACCEPTANCE
- [x] Location ask shows the new question and the two chips; nothing else shows them
- [ ] Yes chip → browser location prompt → real `lat`/`lng` reach the API (ticket gets GPS)
- [x] No chip → local voice-note bubble + focused input; a following place name is collected normally
- [ ] Typed "हाँ" / "नहीं" handled locally, not sent to the backend
- [ ] Spoken "हाँ" / "नहीं" handled after transcription, no duplicate re-ask bubble (needs a human at the mic)
- [x] Validator rejects `location: "हाँ"` / `"नहीं"` (unit tests); existing tests + ruff pass
- [ ] Same in `widget.js`
- [x] A GPS-only turn after an issue was collected reaches `confirm`, not `out_of_scope` (unit test + live)
- [x] Backend routing/jurisdiction code unchanged (diff shows no edit to `jurisdiction.py`, `ticketing.py`)

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S23-1 | Frontend chips + local branch, not a new `ask_for` value | Contract (S01), mock, contract tests and backend stay unchanged; the Lead said not to touch GPS/routing unless required |
| D-S23-2 | Yes/no also handled by text/transcript match | Voice-first users will say "हाँ" instead of tapping |
| D-S23-3 | Validator guard for yes/no words | Without it a spoken "हाँ" can become a fake location |
| D-S23-4 | Yes/no word lists are constants in the frontend and validator, kept in sync by hand | No build step / shared module (PROJECT.md §9) |

## BUILD LOG (29 Sep 2026)
Verified live (real backend + Chrome): location ask shows the new question and both chips; **Yes** (geolocation stubbed to
a Bhopal coordinate) sent `lat`/`lng` and reached `confirm` after the `service_id` fix (§5b); **No** removed the chips,
showed the local voice-note bubble and focused the text box. Backend: 241 pytest passed, ruff clean.
**Not verified:** a real browser geolocation permission prompt and real GPS accuracy; typed "हाँ/नहीं" interception and
spoken "हाँ/नहीं" after transcription (logic written, not exercised); `widget.js` (same code, syntax-checked only).
The pre-existing T13 sentences still expect `ask_for == "location"`, unaffected.
