# S25 — Warmer replies (acknowledgement line, friendlier out-of-scope, honest greeting)
Implements: `backend/app/turn_engine.py`, `backend/app/validator.py`, `specs/water_supply.yaml`,
`frontend/app.js` + `widget.js` greeting · Depends on: S05, S07, S03 · Version: v1 · Status: Draft

## 1. Goal and the line we do not cross
Make the bot feel less mechanical without letting a language model write facts. Today every reply is a fixed
string from the spec. The Lead asked for a more human feel; the safe slice for the freeze is:

1. **An optional one-line acknowledgement** the LLM writes, placed *before* the spec's own question.
2. **A friendlier out-of-scope reply** (spec YAML text).
3. **An honest greeting**: it must stop promising information about "any government service".

Not in this ticket: answering free-form side questions (needs an approved FAQ list), a second service, LLM-written
questions. Facts, fields, questions, routing, confirmation and ticket text stay backend-owned.

## 2. Acknowledgement line
- `TurnResult` gains `ack: str | None`. The Turn Engine prompt adds an optional `"ack"` key: one short sentence in
  Devanagari Hindi (max 12 words) acknowledging what the citizen just said, **only when this turn gave new information**,
  never a question, never a promise, never a fact about offices, dates, officers, numbers or ticket status. `null` otherwise.
- The validator sanitises it deterministically (`_clean_ack`): must be a string; trimmed length 3-120; no `?` or `？`;
  no URL (`http`, `www`); no run of 4+ digits; otherwise it is dropped silently. The LLM is never trusted for this text.
- Composition: on an `ask` action, `reply_text = "<ack> <spec question>"`. On confirm, submitted, out_of_scope and error
  the ack is **not** used (confirm/submitted wording carries facts, S04/S10). No LLM call happens on GPS-only turns,
  so no ack there.
- Fallback: any missing/invalid ack = today's exact text. Providers failing = today's 503 path. No new failure mode.
- History impact: the stored `reply_text` includes the ack. S20's restart boundary uses the *restart* reply, which
  never has an ack, so it is unaffected.

## 3. Out-of-scope wording (spec YAML, `out_of_scope.reply`)
- hi: `माफ़ कीजिए, अभी मैं सिर्फ़ पानी से जुड़ी समस्याएँ दर्ज कर सकता हूँ। बिजली, सड़क जैसी दूसरी समस्याओं के लिए कृपया संबंधित विभाग से संपर्क करें। पानी की कोई समस्या हो तो मुझे बताइए।`
- en: `Sorry, I can only register water-related problems right now. For other issues such as electricity or roads, please contact the concerned department. If you have a water problem, tell me.`
No phone numbers or names: none are verified for this project (S09 rule: never invent).

## 4. Greeting
Remove "ask me for information about any government service" (hi, en, and the spoken Hindi line). New meaning: tell me your
water problem; we route it to the right office; speak or type.

## ACCEPTANCE
- [x] Valid ack + missing field → reply is `ack + spec question` (unit test)
- [x] Invalid acks dropped: question mark, URL, 4+ digits, too long, too short, non-string (unit tests)
- [x] No ack on confirm/submitted/out_of_scope; no ack when the LLM returns none → exact old text
- [x] Prompt contains the ack rule; existing turn-engine tests and the whole backend suite pass; ruff clean
- [x] Live: a real complaint gets a natural Hindi ack before the question; at least 5 real turns read back and judged
- [ ] T13 runner re-run: score not worse than 11/15 (the ack must not disturb extraction); both result files kept
- [ ] Out-of-scope reply and greeting show the new wording in the browser

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S25-1 | The LLM writes only the ack, never the question or any fact | Keeps the "LLM never invents" rule (PROJECT.md §4) while adding warmth |
| D-S25-2 | Deterministic sanitiser + silent fallback | A bad model output must degrade to today's behaviour, not to an error |
| D-S25-3 | Hindi only | TTS is hi-IN fixed (S17 D-S17-1); mixed scripts would be spoken badly |
| D-S25-5 | Promise/action words are blocked in the ack (`ACK_BLOCKED_WORDS`); a final "।" is added if missing | Live check showed the model writing "हम देख रहे हैं" and running the ack into the question |
| D-S25-4 | Ack on `ask` turns only | Confirm/submitted text carries facts and is spec-owned |

## BUILD LOG (29 Sep 2026)
Backend 258 pytest passed, ruff clean. Live (real Groq): 6 real complaints read back after the promise-word filter and
punctuation join: replies were "समझ गया, <the citizen's own symptom>।" + the spec question, no promises. The *first*
live pass showed two defects the unit tests could not (a promise "हम देख रहे हैं", and an ack running into the
question), which is why D-S25-5 exists.
**T13 re-run (run 3): 9/15**, files kept. Not a clean before/after: 3 of the 15 were `503` (see below), so 9/12 of the
answered sentences passed vs run 2's 10/13. The remaining misses are the same three as before (T09-01 generic-word
location, T09-04 and T09-14 vague, asked for the issue). The ack did not visibly change extraction, but the run is too
noisy to *prove* that.
**Not verified:** out-of-scope and greeting wording in a browser (text confirmed in the served files only).

## FINDING: LLM availability is a demo-day risk
Checked directly (29 Sep, one minute apart): **Groq `openai/gpt-oss-120b` returned `429 Too Many Requests` after ~11
consecutive calls** (free-tier rate limit), and its real-prompt latency ranged 1.8-5.9 s against the 6 s timeout.
**Gemini `gemini-3.6-flash`, the fallback, returned 503 "high demand" or timed out on every call.** So under a burst
the "both LLM providers failed" 503 is expected, not a bug. Options (not done, need a decision): check Groq's limits
for the key/tier; lower the model's reasoning effort or pick a faster model; retry once on 429 honouring `retry-after`;
replace the Gemini model id with a less loaded one; keep judges' demo traffic low and warm the model first.
