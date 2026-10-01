# S30 — Intake v2: Jev decides the department, a short guided conversation, Human Evaluation (BUILT behind a switch, 2026-10-01)

Status: **implemented, OFF by default** (`INTAKE_V2`). Lead's decision on the flow, 2026-10-01. Code: `backend/app/intake.py`, `backend/app/jev.py`, three
hooks in `backend/app/routes.py`. Tests: `backend/tests/test_intake.py` (31). Evidence and research: `local-research/AI_GUIDED_INTAKE_DESIGN.md` (git-excluded).

## 1. Goal
A rural citizen describes a problem in their own dialect. Samadhan finds the right department, asks only what is still needed (a few short questions),
and hands what it cannot place to a person. Jev (TypeSafe) is trusted for **decisions only**; the LLM only extracts text and phrases replies; code owns the flow.

## 2. Flow (Lead's decision)
1. **Jev picks the department** from `specs/registry/departments.yaml` (49 departments) in one call (a Choice plus an urgency yes/no).
2. **Confident** (Jev confidence >= 0.8): continue. A department with a service spec (water, electricity, roads, sanitation) uses that spec. Any other department
   goes to **Human Evaluation** (service `human_evaluation`) with the suggested department recorded (`department_not_live`): a person assigns it.
3. **Not confident**: ask **one** yes/no question about the department Jev suggests most ("क्या आपकी समस्या X विभाग से जुड़ी है?"). Yes confirms it. No (or anything
   else) sends the complaint to Human Evaluation as `department_unconfirmed`: **Human Evaluation**. Never a second department question.
4. When every required detail is in, **once each**: if the place is unclear (no GPS and no office match) ask district / tehsil / nearest town; then ask for how
   many days the problem has lasted ("पता नहीं" is accepted). At most 3 questions per complaint in total.
5. **Safety:** an urgent message keeps the fixed safety line (S28 Q4) on every question.
6. **Fail open:** switch off, no key, no `human_evaluation` spec, or Jev unreachable: the turn behaves exactly as before (existing LLM path). The chat never breaks because of Jev.

## 3. Configuration and privacy
`INTAKE_V2=1` **and** `TYPESAFE_API_KEY` must both be set (`TYPESAFE_MODEL` optional, default `jev-latest`). Names are in `.env.example`; never commit the key.
Only the citizen's message and the last 4 turns are sent to TypeSafe, nothing is logged by the client (not the text, not the key). **Do not enable on real citizen
data before TypeSafe's data terms are read and a decision is made** (retention is unspecified in their docs; zero-retention is an enterprise option).

## 4. Data and contract
- State lives in `collected_fields["_intake"]` (kept by the validator, hidden from the LLM prompt, copied into `tickets.fields`). Keys: `jev` (top 3 with
  probabilities), `jev_confidence`, `pending_dept`, `questions_asked`, `confirmed_by_citizen`, `reason`, `suggested_department`, `location_detail`,
  `asked_location_detail`, `asked_duration`.
- `reason` values: `confident`, `confirmed_by_citizen`, `department_not_live`, `department_unconfirmed`. No schema change: Human Evaluation tickets are already `needs_review`. (General Triage was renamed to Human Evaluation by S31.)
- API contract: additive only. `ask_for` (free text) gains `location_detail` and `duration_days`; `service` is reused for the department question.
- Specs: optional `duration_days` added to `roads.yaml` and `human_evaluation.yaml` (was `general.yaml`) (the other three already had it).
- Dashboard: the ticket detail shows the notes ("AI intake notes"); the CM-office Human Evaluation page presents the `needs_review` queue.

## 5. What was measured (synthetic dialect messages, real Jev; `local-research/scripts/measure_intake_flow.py`)
183 unique messages, truthful simulated citizen: **89%** routed with no question (97.5% correct, and all four misses are label errors on review); **11%** asked the
one department question (0.11 per complaint); about **4%** end in Human Evaluation. **35% of confident routes belong to departments with no spec yet**, so they land in
Human Evaluation with the right suggestion: the real bottleneck now is onboarding departments (spec and offices), not the AI.
Dry end-to-end (`local-research/scripts/e2e_intake_dry.py`, real LLM and Jev, in-memory session, ticket creation stubbed): three dialect conversations behaved as above.

## 6. Not done / limits
- Evidence is synthetic; real dialect conversations and speech-to-text on real dialect speech are the next test.
- The department question names the department, not the problem; Hindi problem hints per department are not written yet.
- Jev is literal (generic words like "our village" are not a place): place extraction stays with the LLM, plus the existing generic-place guard.
- No redaction before sending text to TypeSafe. No per-department tie-breaker questions yet (the CM dashboard's Human Evaluation page lists the department pairs worth writing).
- Departments without a spec cannot be routed to an office: Human Evaluation with a suggestion until their spec and offices exist.

## ACCEPTANCE
- [x] Off by default: all 415 pre-existing backend tests pass unchanged.
- [x] Confident live department -> its spec; confident other department -> `human_evaluation` + suggestion.
- [x] Unsure -> exactly one department question; yes -> that department; no -> `human_evaluation` + `department_unconfirmed`; never a second question.
- [x] Location detail and duration each asked at most once, only at the confirmation step, never when GPS / duration is already known.
- [x] Jev failure -> existing behaviour; text and key never logged; internal notes never reach the LLM prompt.
- [ ] Real dialect conversations reviewed (pending: the Lead is arranging them).
