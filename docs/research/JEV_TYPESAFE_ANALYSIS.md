# Jev (TypeSafe AI) — can it improve Samadhan's understanding, routing and decisions?

Research only, 29 Sep 2026. No production code touched, **no Jev call was made** (see section 7).
Product context: `docs/PROJECT.md`, `docs/specs/S28-multi-department-routing.md`.

**Verdict: EXPERIMENT FIRST.**
**The one problem Jev might solve better than our LLM: a calibrated probability per department/intent.**
Our routing thresholds (0.8 route, 0.5 reconfirm) gate on a number the LLM invents about itself. Jev
returns real per-option probabilities. Whether they are actually calibrated, or usable on Hindi/Bundeli,
is unproven, and no source tests either.

---

## 1. What Jev is

TypeSafe AI's first "System One Model" (early access, hosted API only). It does not write text. It
reads a state (string, JSON or array of strings, text only) and answers a fixed set of typed questions
in one parallel pass. Trained with what TypeSafe calls RLCD (reinforcement learning for calibrated
decisions).

| Primitive | Returns |
|---|---|
| `Choice` (2–255 options, each described in words) | `choice`, probability per option, `confidence` 0–1 |
| `Score` (2–10 ordered levels) | `score` (can be fractional), probability per level, `confidence` |
| `Noul` (yes/no) | `noul` = P(yes); no confidence field |

Endpoint `POST https://api.typesafe.ai/v1/systemone`; Python (`typesafe-sdk`) and JS SDKs; model pin
e.g. `jev-1.13.0` (`jev-latest` moves).

Published numbers (all from TypeSafe or people repeating them):
- Latency 70–500 ms end to end. Price $0.042 / M input tokens, output free.
- Limits: 250k tokens/s, 1,200 requests/min, 64k tokens per call (32k for state + one question).
- Hosted in the US West Coast. No self-hosting. Rate limits and pricing may change, since the
  pricing itself is described as possibly subsidised.

Stated limitations: no string generation; literal reading (negations and scoping words); cannot count or
do date maths; accuracy drops as irrelevant state piles up; the schema guarantee only rules out invalid
values, it can still return a **wrong valid** one.

## 2. What Jev can do (relevant to us)

Read a chat state plus a list of questions and return, in one ~100–500 ms call: which of N options fits
(with the full probability spread), how strongly a yes/no holds, an ordered urgency-style score. Several
questions run in the same call.

Cannot do: extract a ward/colony name, write the Hindi `ack`, propose `info_url`, generate any text.

## 3. Where Jev could help Samadhan

What we have today (from the code): one LLM call per turn (`turn_engine.py`), Groq `gpt-oss-120b` plus
two more Groq models, then Gemini, each with a 6 s timeout. It returns strict JSON with `intent`,
`service_id`, self-reported `confidence`, `candidates`, `fields`, `confirmed`, `urgent`, `ack`,
`info_url`. `validator.py` applies fixed thresholds (`CONFIDENT=0.8`, `RECONFIRM_MIN=0.5`), then decides
route / reconfirm / clarify / general / info reply / out-of-context, and asks the first missing required
field from the spec. Jurisdiction (`jurisdiction.py`) is GPS haversine plus `rapidfuzz` on office names.

| Task | Jev fit | Reason |
|---|---|---|
| 1. Complaint / information / out-of-context | **Good candidate** | Pure 3-way `Choice`. Probabilities show near-ties, e.g. the vague "बहुत परेशानी है यहाँ", which the eval saw declined as chit-chat. |
| 2. Complaint type (issue_type enum) | Possible, low value | Our enums are 3–6 values, already constrained by the spec; the LLM has to run anyway to extract fields. |
| 3. Department | **Best candidate** | `Choice` over 5 services; top-1 vs top-2 probability margin could drive reconfirm/clarify better than a self-reported 0.8. |
| 4. Conversation-state decisions | Partial | `Noul` for "is this a reply to the bot's last question?" and "does the citizen plainly agree with no correction?" is a decent fit. Jev has no memory: we must pass the last turns each time. Its literal-negation weakness hits "हाँ, पर नहीं…" corrections. |
| 5. Missing-information detection | **No** | Already deterministic (`_first_missing_required` against the YAML spec). An LLM/Jev would only make it less predictable. |
| 6. Clarification decisions | Same as 3 | Jev supplies the probabilities. The question text stays fixed, written by us (D-S28-2). |
| 7. Routing decisions | No (see 4) | Department yes; office no. |
| 8. Confidence-based decisions | **The real differentiator** | Calibration is the entire pitch. It is also the least verified claim. |
| 9. Second opinion / validation | Good fit | An independent model with an independent quota that can veto or flag disagreement (route to reconfirm/`needs_review`). |

Operational side benefit (documented by us, not by TypeSafe): S28 measured Groq free tier at 8,000
tokens/min per model, ~1,800 prompt tokens per turn, and a 503 rate of 3/15 in T13 run 7. A small Jev call
would sit outside that quota.

## 4. Where Jev should NOT be used

- **Jurisdiction and office selection.** GPS-to-ward and ward-name matching are already deterministic
  and explainable against authoritative rows in `offices`. A probabilistic model has no ground truth for
  which Bhopal ward office covers a colony, and would blur the "the LLM must never invent offices" rule.
- **Required-field logic, ticket creation, status, validator invariants.** All spec-driven.
- **Field extraction** (location text, duration): needs string output.
- **Any citizen-facing text, `ack`, `info_url`.** Jev generates nothing.
- **Replacing the current LLM.** It cannot do half the JSON we ask for.
- **Emergency (`urgent`) as the only guard**: keep the LLM flag; a Jev `Noul` could add a second
  detector, but never remove one.

## 5. Jev vs current LLM vs both

| | Current LLM | Jev | LLM + Jev |
|---|---|---|---|
| Understands Hindi/Hinglish/Bundeli | Yes, measured: hand 25/26, synthetic 29–30/34 (S28 evals; synthetic caveat) | **Unknown.** No multilingual evaluation exists in any published source; one secondary source says non-English is "handled but not equally well" | Same as LLM for language; Jev only judges |
| Valid structured output | Pydantic + fallback chain; bad id → next provider | "0% errors by construction" | We already handle this, so **no real gain** |
| Wrong-but-valid label | Possible | Possible (their own docs say so) | Disagreement is a useful signal |
| Confidence | Self-reported, uncalibrated (live runs never hit the 0.5–0.8 band, only unit tests) | Per-option probabilities, claimed calibrated, **never independently tested** | Best available, if it checks out |
| Latency | 1–6+ s, retries across providers | 70–500 ms claimed | Run in parallel, so no added latency |
| Quota / cost | Free tier, ~3–4 turns/min/model | $0.042/M in, 1,200 req/min | Removes some pressure only if Jev takes the classification work |
| Field extraction, Hindi replies | Yes | No | LLM only |
| Reliability / risk | Three Groq models + Gemini | Early access, single vendor, closed API, US hosting, no production track record | Jev must be optional (fail open) |

**Structured JSON vs Jev's typed output.** "Choice/Score/Noul is safer than JSON" does not help us: we
already reject invalid ids and clamp confidence. The genuine differences are (a) probabilities instead
of a self-declared number, (b) speed, (c) a separate quota. Everything else is a wrong-valid-label risk
we share with any model.

## 6. Recommended architecture (if the experiment passes)

Do not over-engineer. One optional advisory call, in parallel with the existing LLM call:

```
message + session state + last ~4 turns
   ├─► existing LLM turn (unchanged)
   └─► Jev: intent Choice, department Choice, (optional) confirm_agree Noul, urgent Noul
validator (unchanged rules) + one new input: the calibrated department probabilities
   • Jev and LLM agree, p >= t_high  → route as now
   • disagree or margin < t_margin   → reconfirm/clarify from spec labels (existing path)
   • Jev unavailable / timeout 1 s   → today's behaviour exactly
jurisdiction, offices, required fields: deterministic, untouched
```

Jev never writes state and never chooses an office. Thresholds must be set on our own labelled data and
the model version pinned. Fail open, with a feature flag. It would also need a README attribution entry
and a decision on sending citizen text (place names, complaint content, no contact details) to a US
startup.

## 7. Experimental results

**None. Nothing was measured.** Reasons: Jev is early access behind a waitlist, and there is no
TypeSafe key in our environment (`.env` names checked, no such variable). Everything about Jev's
behaviour above is TypeSafe's claim or a secondary blog's, not something we verified.

Proposed experiment, about half a day once access exists, run outside the submitted tree:
1. Reuse the labelled sets we already have: `run_routing_eval.py` (60: 26 hand + 34 synthetic
   Bundeli/Malvi), `submission/T09-test-sentences.json`, T13's 15.
2. Ask Jev intent + department; record top-1 accuracy against our labels and against the LLM's results
   in `submission/routing-eval-results-run*.json`.
3. **Calibration check:** bin by Jev confidence, compare accuracy per bin; do the same for the LLM's
   self-reported confidence. This is the go/no-go test.
4. Check the known failures: vague sentence, document-name complaints, pump-motor sentence,
   side-question mid-complaint.
5. Measure real latency from Bhopal to a US West Coast endpoint.
6. Pass criteria (proposed, agree before running): equal or better exact-match accuracy on the Hindi
   sets, and clearly better-separated accuracy per confidence bin than the LLM's number. Caveats stay:
   the synthetic set was written by an LLM, not checked by native speakers, and the sample is small.

## 8. Final recommendation

**EXPERIMENT FIRST.** Do not integrate before the 30 Sep noon submission. `CLAUDE.md` and PROJECT.md
freeze the code until 10 Oct, and there is no access or data to justify it anyway. This is a roadmap
item, not a submission feature. After the event, if the calibration test passes, upgrade to
**USE FOR SPECIFIC TASKS**: an advisory department/intent second opinion feeding the existing
reconfirm/clarify path. It would replace nothing in the current LLM, and touch nothing in jurisdiction.

**What exact problem does Jev solve better than our current model?** Producing a trustworthy
confidence for a fixed set of choices (and doing it fast, on separate capacity). It does not
understand our languages better, does not extract or write anything, and its typed-output guarantee
solves a problem we have already handled. If its calibration turns out to be no better than our LLM's,
the answer is nothing, and the verdict becomes NOT CURRENTLY USEFUL.

## Sources

- [TypeSafe: Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) (primary: latency, price, benchmark bias caveat, limitations)
- [DEV Community: How to Use Jev](https://dev.to/valyuai/how-to-use-jev-a-practical-guide-to-typesafes-system-one-model-g5e) (API shape, limits, stated limitations)
- [TrueFoundry: What "System One Models" actually are](https://www.truefoundry.com/blog/typesafe-ai-jev) (critical view: calibration untested, early access, closed API)
- [DataCamp](https://www.datacamp.com/blog/system-one-models-jev), [MarkTechPost](https://www.marktechpost.com/2026/09/23/a-coding-guide-to-typesafe-ai-jev/) (search results only, not opened)
- Multilingual point: search summaries citing secondary blogs ([Medium](https://medium.com/data-science-in-your-pocket/laya-vs-typesafe-jev-ai-8b5dd9ce0176), [ChatMaxima](https://chatmaxima.com/blog/typesafe-jev-system-one-model/)); not opened, treat as unverified.
- Not checked: TypeSafe's own API docs pages (only the launch blog was read), so limits and pricing above may be stale. Sources also disagree on the early-access date (15 vs 28 Sep).
