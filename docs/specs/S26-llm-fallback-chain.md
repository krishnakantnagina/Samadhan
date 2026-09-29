# S26 — LLM fallback chain (rate-limit resilience)
Implements: `backend/app/turn_engine.py`, `backend/app/config.py`, `.env.example` · Depends on: S05, S04 §5 · Version: v1 · Status: Draft

## 1. Problem (measured, 29 Sep 2026)
- T13 run 3: 3 of 15 requests were `503 both LLM providers failed`.
- Direct check: Groq `openai/gpt-oss-120b` returned **429 Too Many Requests** after ~11 calls in about a minute (free
  tier), latency ranged 1.8-5.9 s against the 6 s provider timeout. Gemini `gemini-3.6-flash` returned 503 "high demand" or
  timed out on every call. Effectively there was **one** working provider, so a burst = 503 for the citizen.

## 2. Measurements behind the design (paced 6 s apart, no 429, 8 T09 sentences)
| Model | Valid JSON | Right `issue_type` | avg / max latency |
|---|---|---|---|
| gpt-oss-120b, default effort | 8/8 | 8/8 | 2.0 / 2.5 s |
| gpt-oss-120b, `reasoning_effort=low` | 8/8 | 8/8 | 1.5 / 1.7 s |
| gpt-oss-20b, low | 8/8 | 7/8 (T09-02 returned no issue) | 1.2 / 1.3 s |
| qwen/qwen3.8-27b | 8/8 | 8/8 | 0.9 / 1.3 s |
A sample of 8 is small: it justifies the *ordering*, it does not prove equal quality on every sentence.

## 3. Design
1. **Chain, in order:** `[GROQ_MODEL (primary), *GROQ_FALLBACK_MODELS, GEMINI_MODEL]` when `LLM_PROVIDER=groq`; with
   `LLM_PROVIDER=gemini` Gemini goes first. Groq applies rate limits **per model** (assumed from its docs, checked live in
   ACCEPTANCE), so each extra Groq model is an extra quota, on the same key.
2. **`GROQ_FALLBACK_MODELS`** (optional, comma-separated). Default: `qwen/qwen3.8-27b,openai/gpt-oss-20b` (fastest and
   accurate first, weakest last). Empty string = no extra Groq models (today's behaviour).
3. **`GROQ_REASONING_EFFORT`** (optional; `low` default, `medium`, `high`, or empty to omit). Sent only to `openai/gpt-oss-*`
   models, which support it; other models never receive the parameter.
4. **429 handling:** a Groq 429 fails the provider immediately (fast, ~0.6 s) and the chain moves to the next model. No
   sleep-and-retry: Groq's retry-after on a token-per-minute limit is usually longer than a citizen will wait, and the next
   model is the better use of that second.
5. **Turn deadline:** `TURN_DEADLINE_SECONDS = 14`. Before starting the next provider, if the elapsed time since the turn
   began is already at or above the deadline, stop and raise `TurnEngineUnavailable` (the existing 503). Bounds the worst
   case (4 slow providers x 6 s) at roughly one extra provider timeout past the deadline instead of 24 s.
6. **Logging:** every provider failure is logged at WARNING with the provider/model and the reason (status code or
   exception type), the lesson of G-S16-1 (silent failures hid the cause of the 503s for a day). No prompt or citizen text in logs.
7. **Structural validation unchanged (S05):** a model that returns invalid JSON or an unknown service id counts as a failure
   and the chain continues.
8. **A second Groq *account* key is not used.** Rotating accounts to avoid a rate limit is against the spirit of the
   provider's terms and is out of scope. The Lead's pasted key must be rotated (it was exposed in chat).

## 4. Out of scope
- Paid-tier upgrade, request queueing, per-IP rate limiting of our own API (G-S17-1).
- Changing the Turn Engine prompt or the ASR (Sarvam/Whisper) chain.
- Choosing a new Gemini model id (503 there is provider load, not our config; re-check before demo day).

## ACCEPTANCE
- [x] `default_providers` order is right for both `LLM_PROVIDER` values and with an empty fallback list (unit tests)
- [x] `reasoning_effort` is sent to gpt-oss models only, and only when set (unit test on the request body)
- [x] A 429 moves on to the next provider without sleeping; a provider that fails is logged (unit tests)
- [x] The deadline stops the chain (unit test with a fake clock/providers)
- [x] Config parses/defaults the two new env vars; `.env.example` documents them
- [x] Full backend suite + ruff pass
- [x] **Live:** hammer the primary model until it returns 429, then confirm a turn still succeeds via a fallback model
      (this is what proves the per-model quota assumption)
- [x] T13 re-run: no more `503`s from rate limiting; score reported honestly next to runs 1-3

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S26-1 | Extra Groq models, same key | Per-model quotas + no terms risk; measured accurate and faster |
| D-S26-2 | `reasoning_effort=low` default for gpt-oss | 25-30% faster in the sample with no accuracy loss; configurable, one env var to undo |
| D-S26-3 | No retry-after sleep on 429 | Falling through to the next model is faster and keeps the citizen's wait bounded |
| D-S26-4 | Turn deadline of 14 s | The citizen's total wait stays bounded even when providers time out rather than fail fast |

## BUILD LOG (29 Sep 2026)
Backend: 274 pytest passed (12 new in `tests/test_llm_chain.py`), ruff clean.
**Live proof of the per-model quota assumption:** with the real key, `openai/gpt-oss-120b` returned 429 after 10
back-to-back calls (`retry-after: 2`); the very next real turn through the default chain succeeded in 1.4 s via a
fallback model, with a WARNING log naming the reason. Note the observed `retry-after` was 2 s, shorter than D-S26-3
assumed; falling through is still the faster choice, so the decision stands.
**T13 run 4 (`submission/T13-prompt-test-results-run4-after-s26-chain.json`): 9/15 with zero 503s.** Runs 3 and 4 have the
same score for different reasons: run 3 lost 3 sentences to 503; run 4 answered all 15 and the misses are real accuracy:
T09-01 (generic word stored as location), T09-04/13/14 (vague or irregular-supply sentences: the model asks for the issue),
T09-11 (drainage, `out_of_scope`), T09-15 (`other` instead of `no_supply`, likely a fallback model answering under the burst).
So the chain fixes availability, not the accuracy gap; the T13 target of 13/15 is still not met.
**Not verified:** behaviour in a real browser session under many concurrent users; the Gemini model id (still overloaded).
The Lead's second Groq key was deliberately not used (section 3.8); it should be rotated.
