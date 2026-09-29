# S21 — Prompt tests (Turn Engine accuracy on real sentences)
Implements: T13 (`backend/tests/prompt/run_t13.py`) · Data: `submission/T09-test-sentences.json` · Depends on: S05, S04 ·
Version: v1 · Status: Draft

## Purpose
T13's done-when is **≥ 13/15**. It measures whether the real Turn Engine (real Groq/Gemini, real prompt,
real validator, real Supabase) extracts the right `issue_type` and `duration_days` from 15 Bundeli-dialect
water complaints. It is a live accuracy check, not a unit test: it is **not** collected by `pytest`
(file is `run_t13.py`, not `test_*.py`) because it calls paid/rate-limited external APIs.

## Method
For each sentence: a fresh `session_id`, one `POST /api/v1/message` (text) through the real app, then read
that session's `collected_fields` from Supabase (an `ask` response carries no `summary`, so the DB row is
the only place the extracted `issue_type` is visible).

## Grading (per sentence, all must hold)
1. `action == "ask"` and `ask_for == "location"` (none of the sentences names a place).
2. `collected_fields.issue_type` is in the sentence's **accepted set** (below).
3. If `expected_fields` lists `duration_days`, it equals it exactly.
Any other extra field is ignored. A provider failure (503) counts as a fail and is reported as such,
not retried silently.

The T09 file says the ambiguous sentences "should not be hard-failed on an exact match", so their accepted
set is every value its notes call reasonable. Fixed here, before running, so the sets can't be tuned to the results:

| ID | Accepted `issue_type` |
|---|---|
| 01, 02, 05, 09, 14, 15 | `no_supply` |
| 07 | `leakage` |
| 10 | `low_pressure` |
| 12 | `dirty_water` |
| 03 | `no_supply`, `low_pressure` |
| 04, 06, 08 | `no_supply`, `other` |
| 13 | `low_pressure`, `other` |
| 11 | any of the 5 valid values (notes: not a clean fit to any) |

## Output
Console table + `submission/T13-prompt-test-results.json` (per-sentence input, response, extracted fields,
pass/fail, reason, model/provider used, timestamp). A failure is **reported as-is**; the prompt is only
changed afterwards if the failures show a real prompt defect, and then the run is repeated and both
results are kept. A low score may be a dialect gap, not a broken extractor (T09 `_meta.dialect`).

## ACCEPTANCE
- [ ] Runner completes all 15 with real providers
- [ ] Results file written
- [ ] Score ≥ 13/15, or the failures are analysed honestly in the results and build log

## RESULTS (29 Sep 2026, Groq `openai/gpt-oss-120b`, real Supabase) — target NOT met
| Run | Score | Files |
|---|---|---|
| 1 — original prompt | **11/15** | `submission/T13-prompt-test-results-run1-before-prompt-fix.json` |
| 2 — after adding the "generic word is not a place name" rule to `turn_engine.py` | **10/15** | `submission/T13-prompt-test-results-run2-after-prompt-fix.json` |

Failures, by cause (not tuned away — the grading table above was fixed before run 1):
1. **Generic word stored as a location (real defect).** T09-01 (`location='गाँव'` / `'हमाए गाँव'`) and T09-10
   (`location='हैंडपंप'`) skipped the location question and went straight to `confirm`. A ticket from that would
   route to the district office with a useless location. The prompt rule fixed T09-10 but T09-01 still failed in
   run 2, then passed on a manual retry: the model is non-deterministic on it, so a prompt rule alone is not a reliable fix.
2. **Provider failures, not accuracy.** Run 2 had two `503 both LLM providers failed` (T09-12, T09-14). Cause not yet investigated.
3. **Vague sentences the model declines to guess.** T09-04 (run 2) and T09-14 (run 1) → asked for `issue_type`
   instead of location. Arguably correct behaviour (T09-04's own note allows a follow-up), but fails the pre-set rule.
4. **T09-11 (drainage)** → `out_of_scope`, in both runs. Arguably the *right* answer for a drainage complaint;
   fails only because the grading table said any valid `issue_type`.

### Run 3 (after S25 warm replies): **9/15**, `submission/T13-prompt-test-results-run3-after-s25.json`
3 of 15 were `503` caused by Groq `429` + Gemini overload (see S25 FINDING), so the honest reading is 9/12 answered.
Same three substantive misses as run 2. Target still not met.

### Run 4 (after S26 fallback chain): **9/15**, zero 503s, `submission/T13-prompt-test-results-run4-after-s26-chain.json`
All 15 answered. Misses are accuracy, not availability (T09-01, 04, 11, 13, 14, 15; details in S26 BUILD LOG). Runs 1-4:
11, 10, 9, 9. The 13/15 target is not met and the remaining gap needs prompt/spec work or a decision on the vague and
drainage sentences, not more infrastructure.

### Runs 5 and 6 (after S27 generic-place guard): **13/15** and **12/15**
Zero 503s. T09-01 and T09-10 now pass every time. Remaining misses: T09-04 and T09-14 (vague; the model asks for the issue), and
T09-11 (drainage) which flips between pass and fail. Full analysis in S27 BUILD LOG. Target met once, missed once.
