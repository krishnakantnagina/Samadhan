# S33 — Triage questions: ask what a person would ask (BUILT behind a switch, 2026-10-03)

Status: **implemented, OFF by default** (`TRIAGE=1`, and it needs `INTAKE_V2=1`). Code: `backend/app/triage.py`, hooks in `backend/app/intake.py` (prestep, poststep) and one
argument in `backend/app/routes.py`. Tests: `backend/tests/test_triage.py` (28). Question bank: `local-research/question-bank/` (git-excluded drafts, see its README).

## 1. Goal
"School" is only a place. WHO did WHAT and HOW BAD decide the right desk and how fast it must move. After the story is clear the bot asks the few questions a kind
call-centre person would ask, one per turn, in warm spoken Hindi, and stores the answers and a seriousness level with the ticket for the officer.

## 2. Flow (code owns it, the LLM only reads)
1. Intake v2 decides the department (S30). Triage uses `suggested_department` (set for every department, also those without a spec: they land in Human Evaluation,
   where the notes help the person) or the department of the live spec. **If the department is only a guess (`department_unconfirmed`) triage stays out.**
2. At the confirm step, BEFORE the district/tehsil and duration questions: one LLM call (the Turn Engine's provider chain) reads the story, picks the category of that
   department and any answers already given ("the boy is hurt" answers the injury question). Category confidence under 0.6, no bank, or LLM down: triage is skipped.
3. Up to `TRIAGE_MAX_QUESTIONS` (3) questions, seriousness first, then routing, then detail. Answered questions are never asked. Place and duration questions are
   dropped from the bank: the existing steps ask those. A question left unanswered ("don't know") is never asked twice.
4. Every reply is read by the same call (it also catches extra details). A reply to our question is **pinned to the complaint in progress**: the turn engine once read
   "the child's arm is swollen" and "I don't know" as chit-chat and sent the out-of-scope reply mid-conversation. The same pin now protects the district and duration answers.
5. Seriousness low / medium / high / urgent is judged by the LLM from the bank's rule sentence; **urgent is only allowed where the category defines an escalation**
   (else capped at high). Urgent keeps the fixed safety line (S28 Q4) on every later question. **No phone number is ever read to the citizen** (project rule: none verified);
   the bank's escalation note is stored for the officer only.

## 3. Human talk
A warm opener before each question (plain: "ठीक है, समझ गया।", worried when the case is serious: "ओह, यह तो चिंता की बात है।", later: "जी, धन्यवाद।"), the last question
is introduced ("आख़िरी बात, ..."), and each question is spoken in its conversational rewrite (`ask_hi`, written once by Gemini, 804 of 808 questions) instead of the form wording.
Choice is deterministic (no randomness), so the same story always gets the same wording.

## 4. Data
`collected_fields["_intake"]["triage"]`: `dept`, `category`, `category_confidence`, `asked`, `answers` (question id -> value), `pending`, `severity`, `reason`, `done`,
`escalation_note` (high/urgent only), `skipped` (`no_bank` | `llm_unavailable` | `category_unclear`). Copied into `tickets.fields` with the other intake notes. No schema change.
API: `ask_for` gains the free-text value `triage` (additive).

## 5. Measured (5 simulated villagers, real LLMs, nothing stored; local-research scratchpad)
Teacher beat a child, scholarship, no medicine, ration refused, cattle disease: relevant questions each time, 1-3 per complaint, severity low/medium/urgent as expected
(the injured child = urgent with the officer note). Found and fixed: wrong-department questions after an unconfirmed guess; the out-of-scope reply to a plain answer.

## 6. Not done / limits
- The bank is a Gemini DRAFT nobody reviewed (severity rules especially). Do not enable for real citizens before a teacher / doctor / police officer / caseworker reads it.
- The bank folder is not in `specs/`: copy `local-research/question-bank/*.json` to `specs/triage/` (or set `TRIAGE_BANK_DIR`) once the Lead approves committing it.
- Extra LLM calls: one at the first triage step and one per answer (about 1-3 s each); with 3 questions that is up to 4 calls on top of the Turn Engine's.
- The LLM sometimes misses an answer the story already gave (asked "more than one animal?" after "many cows died").
- The fixed safety line is repeated on EVERY question of an urgent case (S28 Q4). It reads robotic after the second time; saying it once and again only on escalation is
  a decision for the Lead.
- The dashboard does not show seriousness or sort by it yet; officers see the notes in the ticket detail ("AI intake notes").
- Question order inside a priority is the bank's order; some severity questions are judgements a villager cannot make ("does he need a hospital?").
- Sexual abuse of a child is not a category: it needs a protected flow written with a child-protection officer.
