# S35 Understand first (translate, then decide what the message is)

Status: built 5 Oct 2026, local branch `post-submission`, **off by default** (`UNDERSTAND_FIRST=1` + `GEMINI_API_KEY`). Code: `backend/app/understand.py`, wiring in `backend/app/routes.py` (step 5d, 6a).

## Why
Dialect words confuse the department router (Jev) and the turn engine. Example: "हमारे गाँव में मारसाब नहीं आ रहा" (the teacher, "master sahab", is not coming): Jev answered
health 0.44 (unsure) and the engine matched "नहीं आ रहा" to water. Gemini reads it correctly ("मास्टर साहब (शिक्षक) नहीं आ रहे हैं", complaint, 0.98). A vague first message ("I have a problem")
is cheaper to clarify once than to route wrongly.

## Flow (only when a conversation starts: no service chosen yet, not awaiting confirmation; never on answers like "हाँ" or a village name)
1. Gemini returns `{language, hindi, english, kind, confidence}` for the message (and the last 4 turns).
2. `kind`:
   - `complaint` (confidence >= 0.5): continue. The turn engine and Jev read the citizen's words **plus** the standard-Hindi/English translation (`understand.engine_text`). Jev picks the department, the usual questions follow (where, how long), then the ticket is routed to the office.
   - `unclear` (or a complaint under 0.5): reply "tell me your complaint again" (`ask_for = complaint`), nothing routed. After 2 asks (`MAX_UNCLEAR_ASKS`) the normal pipeline takes the message instead of looping.
   - `question`, `document_request`: the existing fixed information reply (S28 4.6: validated `.gov.in` link, disclaimer). No ticket.
   - `greeting`: the existing out-of-context reply.
3. S35 overrides the turn engine's own intent guess for these kinds (status questions are untouched).
4. The translation is stored with the ticket notes (`collected_fields._intake._understand`) so the officer sees it.

## Failure
Any Gemini error returns None and the pipeline runs exactly as before. Models: `UNDERSTAND_MODELS` (comma list, tried in order) else `GEMINI_MODEL` then `gemini-3-flash-preview`, `gemini-3.1-flash-lite`
(free tiers answer 429/503 often; each model has its own quota). No new model call after 9 s. Cost: one extra Gemini call per new conversation.

## Not built (ideas)
- Document requests could be answered from the services catalogue (portal, documents, fee, deadline for the 359 notified services) instead of the fixed "no official information" text.
- A mid-conversation message that is a different complaint is still handled by the intake switch guard (only a confident Jev may move the complaint); S35 does not run there.

Tests: `backend/tests/test_understand.py` (17 + chain/deadline tests, fake Gemini).
