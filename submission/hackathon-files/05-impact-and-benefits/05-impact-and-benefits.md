# Impact and Benefits

**Samadhan (समाधान)**

This note separates **what we measured**, **what the design guarantees**, and **what we cannot claim yet**. Numbers marked TBD need real
measurement; we have not filled them with estimates.

## 1. Measured

| Measure | Result | How measured | Caveat |
|---|---|---|---|
| Department routing accuracy | About **90% exact** on 60 messages: hand-written 25 of 26, synthetic Bundeli/Malvi 29 to 30 of 34 | `backend/tests/prompt/run_routing_eval.py`, results in `submission/routing-eval-results-*.json` | One run per data set. Synthetic data was written by an LLM and not checked by native speakers. Remaining misses are mostly debatable labels |
| Water-issue extraction | 12 to 13 of 15 on the two best of six runs (11, 10, 9, 9, 13, 12) | `submission/T13-prompt-test-results-run*.json` | The 13/15 target was met once, not consistently |
| Automated tests | 415 backend + 35 dashboard tests pass; Ruff clean | `uv run pytest` | Tests use no network or keys; they check logic, not live accuracy |
| Definition-of-done scenarios | All ten exercised end to end with real providers; scenario 7 (GPS to the correct ward) cannot pass yet | Scripted run | Ward centre points are not available, so a GPS-only complaint goes to the district office |
| SMS OTP delivery (feasibility only, not in the product) | One real OTP delivered to a real Indian number in about 1 second | Manual test, 30 Sep 2026 | One test; not integrated |

## 2. Guaranteed by design (verifiable in the code and specs)

- **Fewer steps to file.** A citizen who gives everything in one message goes straight to confirmation. The minimum path is
  **describe → confirm → ticket**, two citizen messages (scenario 3 in `docs/PROJECT.md`). Missing details are asked one at a time.
- **No department knowledge needed.** The citizen never chooses a department or a form.
- **No typing needed.** Voice in, voice out.
- **No silent misrouting.** Low confidence goes to the district office as `needs_review`, and every officer correction is logged.
- **No duplicate tickets from retries.** A repeated message ID returns the stored answer.
- **Feedback for the citizen.** A complaint number, and status by typing or saying it.
- **Less triage work for officers.** Tickets arrive with a department, office, summary, audio and a review queue.

## 3. Comparison with existing channels: TBD

`docs/TICKETS.md` (T10) calls for screenshots of the CM Helpline menu bot to count taps and typing. Those screenshots are not in the repo,
so **no tap or typing comparison is made here**. To complete this section: record the number of taps and typed characters to file a water
complaint in the CM Helpline bot, and put them beside Samadhan's two-message minimum.

| | CM Helpline menu bot | Samadhan |
|---|---|---|
| Taps to file a water complaint | TBD | 0 taps required to describe (voice or text), 1 to confirm |
| Typing needed | TBD | None with voice |
| Must know the department or ward | TBD | No |

## 4. What we do not claim
- Any reduction in **resolution time**. That needs real usage over time, not a hackathon pilot.
- Statewide numbers, citizen counts, cost savings or call-centre load reduction. None have been measured.
- Dialect coverage beyond Hindi and Hinglish that a native speaker has confirmed.

## 5. Expected benefits at pilot scale (hypotheses to test, not results)
1. Fewer wrongly routed complaints, measured by the count of officer reassignments in `routing_corrections`.
2. Faster first response, measured by time from filing to first status change.
3. Less officer triage time, measured by time spent on the review queue.
4. Higher filing rate from citizens who avoid forms, measured by complaints filed by voice.
