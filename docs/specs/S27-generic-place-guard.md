# S27 — Generic-place guard (and the S23 decision)
Implements: `backend/app/validator.py` · Depends on: S07 (validator), S23 (location question), S21 (the T13 finding) ·
Version: v1 · Status: Draft

## 1. The defect (T13, runs 1-4)
When a citizen's message contains a generic word ("हमाए **गाँव** में…", "**हैंडपंप** में पानी कम…"), the LLM sometimes stores that
word as `location`. The validator accepted it (2+ characters), so the bot skipped the location question and went straight to the
summary; the ticket then routes to the district office with a useless location, and we store no contact detail to ask again.
A prompt rule (S21 run 2) reduced it but did not remove it (the model is non-deterministic on this).

## 2. Decision
Fix it **deterministically in the validator**, backend only:
`location` is rejected (treated as not given) when **every word** of the value is a generic place noun or a filler word, in
Devanagari or Latin script. The normal location question (S23) is then asked, and its "no" branch already asks for the village or
ward name. A value with any non-generic word is accepted unchanged.

Accepted: `मिसरोद`, `Misrod`, `वार्ड 12` (the number is not generic), `मिसरोद गाँव`, `Kolar Road`, `जाटखेड़ी, वार्ड 29`, `पुराना शहर`.
Rejected: `गाँव`, `हमाए गाँव`, `हमारे मोहल्ले में`, `हैंडपंप`, `हैंड पंप`, `पानी की टंकी`, `our village`, `the village`, `gaon`, `ward`, `घर`.

## 3. Decisions
| # | Decision | Reason |
|---|---|---|
| D-S27-1 | Deterministic word check in the validator, not a better prompt | Two live runs showed the prompt rule alone is not reliable |
| D-S27-2 | Whole-value test (every word generic/filler), never substring | A real name that contains "गाँव" or "Road" must never be rejected |
| D-S27-3 | The list lives **only in the backend** | The S25/S23 ultrareview flagged word lists kept in sync by hand between the frontend and backend as fragile; this adds no such copy |
| D-S27-4 | **The S23 two-question flow (v2) was built, then reverted.** The one-question flow (committed) stays | Ultrareview finding 3 (hand-synced lists drift) applies more to a flow with ~20 extra phrases; Q2 "can you send your location?" duplicates what the browser permission prompt already handles (denied -> Hindi message asking for the ward); two voice questions before every complaint is slow for a villager and for a 3-minute demo |
| D-S27-5 | English/Hinglish storage of the place (`location_en`) is deferred to the post-event roadmap | Not needed for the demo; another prompt+spec change the day before the freeze; does not fix this defect |

## 4. Out of scope
Ward-name validation against `offices` (the jurisdiction resolver already does that later); spelling normalisation; `location_en`.

## ACCEPTANCE
- [x] Rejected examples above return "no location" from the validator and the turn becomes an `ask` for location (unit tests)
- [x] Accepted examples above are stored unchanged (unit tests, incl. names that contain a generic word)
- [x] Full backend suite + ruff pass
- [x] Live: T09-01 ("हमाए गाँव…") and T09-10 ("गाँव के हैंडपंप…") now ask for location instead of confirming
- [x] T13 re-run reported honestly next to runs 1-4

## BUILD LOG (29 Sep 2026)
Backend 296 pytest passed (22 new), ruff clean. **Live T13, same key, zero 503s (S26 chain):**
- Run 5 (`submission/T13-prompt-test-results-run5-after-s27-guard.json`): **13/15**. Misses: T09-04, T09-14.
- Run 6, repeat (`...run6-repeat.json`): **12/15**. Misses: T09-04, T09-11, T09-14.
The systematic defect is gone: **T09-01 and T09-10 (the generic-word sentences) passed in both runs**. What remains:
T09-04 and T09-14 are vague sentences ("big water problem", "trouble getting drinking water in summer") where the model asks for
the issue instead of the location, in every run 2-6. That is arguably correct behaviour, but it fails the pre-set grading rule.
T09-11 (drainage) flips between `leakage` (pass) and `out_of_scope` (fail) from run to run: LLM non-determinism on an ambiguous
sentence, not a code change.
**Honest reading:** the 13/15 target was met once and missed once, so it is "12-13/15, target borderline", not "target met".
If the Lead accepts `out_of_scope` as a correct answer for the drainage sentence (a rule change made after seeing results, so it
is not applied here), both runs would be 13/15. Runs 1-6: 11, 10, 9, 9, 13, 12.
