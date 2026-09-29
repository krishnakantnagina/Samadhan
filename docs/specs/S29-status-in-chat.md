# S29 — Check complaint status in the chat (typed or spoken), status link on the ticket card, general greeting
Implements: `backend/app/status_reply.py` (new), `turn_engine.py` (intent `status`), `validator.py`, `routes.py`, frontend
`app.js` / `widget.js` / `status.js` / `index.html` · Depends on: S11 (status lookup), S20 (commands), S28 (intents), S17 (voice) ·
Version: v1 · Status: Approved by the Lead (29 Sep), built

## 1. Problem (found in a real test, 29 Sep)
A citizen asked by voice "क्या मुझे अपने शिकायत की स्थिति पता चलेगी?" and got the generic "no official information" reply: the bot
had no status feature (status lived only on `status.html`, and nothing in the chat pointed to it). Also the greeting still talked only
about water, although the bot now takes any complaint, and answers enquiries with a link.

## 2. Behaviour
1. **Complaint number in the message → the status, straight away.** If a short message (at most 14 words) contains a complaint number,
   typed or spoken, the bot answers with the status and skips the LLM (no quota used):
   `आपकी शिकायत SMD-0022 की स्थिति: <status>।` / `विभाग: <department>।` / `आखिरी अपडेट: <DD-MM-YYYY>।`
   Not found → `मुझे शिकायत क्रमांक SMD-0099 नहीं मिला। कृपया क्रमांक दोबारा जाँचें।`
2. **A status question without a number → ask for it.** The Turn Engine gets a fourth intent, `status` ("asks about the progress of an
   already filed complaint"). With no number the reply is fixed text asking for it (typed or spoken) and pointing to the header link
   `अपनी शिकायत की स्थिति जानें`. The next message just carries the number, which rule 1 catches, so no session state is needed.
   If the LLM says `status` and the message has a bare number (e.g. "मेरी शिकायत 22 की स्थिति"), that number is used.
3. **Voice access.** Spoken numbers are understood: `SMD-0022`, `smd 22`, `S M D 0 0 2 2`, `एसएमडी 0022`, `एस एम डी शून्य शून्य दो दो`,
   Devanagari digits `एसएमडी ००२२`. Digits and digit words (शून्य/ज़ीरो, एक … नौ, and English zero…nine) after the prefix are joined;
   the first other word ends the number. The number is normalised to `SMD-` plus at least 4 digits (the S01 pattern).
   **Known limit:** a number spoken as a Hindi number word ("बाईस") is not understood; the bot then asks for the number again.
4. **Safe by design.** Only what the public status endpoint already returns (status, department, update time; S11 RULES 2): never fields,
   text, GPS, audio. Anyone with a number could already see this on the status page (S01 §5), so the chat adds no new exposure.
5. **A status lookup never disturbs a complaint in progress.** Same as the information and out-of-context replies (S28 4.6): the session is
   left exactly as it was, and the response uses the existing `out_of_scope` action (no contract change).
6. **Ticket card link.** The ticket card after a submission gets `स्थिति देखें`, a link to `status.html?id=SMD-xxxx`; the status page
   reads `?id=` and runs the lookup on load.
7. **Greeting and header no longer say water.** Hindi, English and the spoken Hindi greeting, the header tagline, and the widget's copy
   now say: tell me your problem or complaint, ask about a government service (enquiry), or check your complaint status.
   The hero preview bubble on the landing page is an example conversation and is left as an example.

## 3. Out of scope
- Looking a complaint up by anything other than its number (phone, name): none is stored (PROJECT.md §8).
- Hindi number words above digits ("बाईस").
- Push notifications when the status changes (roadmap).

## ACCEPTANCE
- [x] Extraction: typed, spaced, hyphenated, Devanagari-digit, letter-by-letter and digit-word forms all give `SMD-00nn`; sentences with no number, or a long complaint that merely mentions a number, give nothing (unit tests)
- [x] A short message with a number returns the status without any LLM call (unit test on the route, LLM patched to fail)
- [x] A status question without a number gets the ask-for-number reply; a complaint in progress is untouched (unit tests)
- [x] Unknown number gets the not-found reply
- [x] Live: a real ticket's status through the chat, typed and in the spoken forms (text path, same code)
- [x] Ticket card link works and `status.html?id=` auto-runs
- [x] Greeting, tagline and widget copy contain no water wording
- [x] Full suites and ruff pass; nothing is committed without the Lead's say-so

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S29-1 | The number is found by a deterministic parser, before the LLM | Instant, free of quota, and IDs are exactly what an LLM gets wrong |
| D-S29-2 | No new session state: the number arrives in the next message | Keeps the flow stateless; a status lookup never resets a complaint |
| D-S29-3 | Reuse the `out_of_scope` action | No contract change (same choice as S28 4.6) |
| D-S29-4 | Short-message rule (14 words) for number detection | A long complaint that mentions a number must not be hijacked |

## BUILD LOG (30 Sep 2026)
Backend 415 pytest passed (42 new in `tests/test_status_reply.py`), ruff clean. **Live (real backend, real ticket `SMD-0022`), text path = the
same code the transcript takes:** typed `SMD-0022`, `S M D 0 0 2 2`, `एस एम डी शून्य शून्य दो दो`, `एसएमडी ००२२` and a sentence containing `smd 22` all
returned the same status (`प्रक्रिया में है`, department, date); `SMD-0999` returned the not-found reply; the real spoken sentence from the Lead's
test ("क्या मुझे अपने शिकायत की स्थिति पता चलेगी?") now gets the ask-for-number reply instead of the generic one; a status lookup in the middle
of a complaint left the complaint untouched (it went on to the summary). **Browser:** the greeting (Hindi and English) and header tagline contain no
water wording; `status.html?id=SMD-0022` fills the box and shows the status on load.
**Not verified:** a real spoken complaint number through the mic (the parser is tested on the forms Sarvam is likely to write, but a real
transcript of a spoken ID has not been seen: check `messages.transcript` if one fails); the `स्थिति देखें` link on the ticket card after a fresh
submission in a browser (code and the `?id=` target verified separately); the widget's copy (same code, syntax-checked only). The landing-page hero
still shows a water-themed example conversation on purpose (it is an example, not the greeting).
