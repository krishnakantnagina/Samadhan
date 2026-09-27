# Samadhan — Jury Q&A Bank

15 likely jury questions with short answers, grounded only in what the prototype actually does
(see `docs/PROJECT.md`, `docs/specs/`, and the tested backend). Where something is roadmap, not
built yet, it's labeled as such — never claimed as done.

## 1. How do you protect citizen data end-to-end?

Postgres RLS is enabled on every table with all default grants revoked — the anon key has zero
access, verified live (`401 permission denied`, not just a filtered empty result). Audio is stored
in a private bucket, served only via short-lived signed URLs. The website itself holds no DB keys
and no business logic — it only talks to the API.

## 2. Does Samadhan comply with India's DPDP Act?

Sessions are anonymous (`session_id` only, no name/phone/OTP collected in M1), and the status
endpoint returns only 4 fields — never transcript, audio, location, or collected details. A full
DPDP compliance review (consent flow, data-retention policy, grievance officer) is roadmap, not
done — we're not claiming certification, only that the data model was built minimal-by-default.

## 3. What does this cost to run and to scale?

Free tiers today: Groq, Gemini, Supabase (Postgres + Storage), Railway/Vercel/Streamlit Community
Cloud. Everything server-side is stateless except the DB, so scaling is mostly a paid-tier upgrade,
not a rearchitecture. One known risk: Supabase's free tier can pause a project after 7 days of
inactivity — worth planning around for any gap between judging rounds.

## 4. How accurate is the AI at understanding citizens?

The Turn Engine never has the final word: everything it extracts is checked against the service
spec before it can be stored (unknown fields or out-of-range values are silently dropped and
re-asked). Real accuracy numbers against a test sentence set are pending (T13) — we'll have this
before submission, and it will be reported as measured, not estimated.

## 5. What happens if the AI routes a complaint to the wrong office?

It's designed not to guess: below a confidence threshold, or when there's no clear ward match, the
ticket is routed to the district office and flagged `needs_review` instead of assigned silently.
Officers can also reassign a ticket from the dashboard, which logs the correction for future
routing improvements.

## 6. Does it handle regional dialects beyond standard Hindi?

M1 targets Hindi and Hinglish (Latin-script Hindi), which is what the pilot test sentences cover.
Broader dialect support depends on ASR provider testing that hasn't run yet — we're not claiming
dialect coverage we haven't verified.

## 7. How do you scale from 5 wards to all 55 districts?

The architecture is built for this: a new service is one YAML file, no code change, and the
jurisdiction resolver reads office/ward data from a database table, not from code. Scaling
statewide means adding verified office and ward data — a data-collection task, not an engineering
rewrite.

## 8. How does this fit with the existing CM Helpline / Customer Solutions Hub?

Samadhan is designed as an additional front door that feeds the same kind of ticket a citizen would
otherwise phone in or type into a WhatsApp menu — it doesn't touch or replace CM Helpline's own
systems. Integrating so tickets land in CSH directly is roadmap, not built.

## 9. Why a website instead of WhatsApp, which citizens already use?

A website let us ship voice, GPS, and a full conversational flow fastest for this pilot, with no
WhatsApp Business API approval or per-message cost in the loop. The core (Turn Engine, validator,
spec format) isn't website-specific — the same engine could sit behind a WhatsApp bot later; that's
explicitly on the roadmap, not a permanent choice.

## 10. What's the plan after 30 Sep?

Per the hackathon rule, nothing changes in the submitted code until the event ends (10 Oct). After
that: real ward centroid data, officer-verified jurisdiction, broader ASR/dialect testing, and — if
selected — a conversation about integration with MPOnline's own systems.

## 11. What if the AI tries to invent a department or field that doesn't exist?

It can't, by construction — the service spec YAML is the only source of valid services, fields, and
departments. Anything the LLM proposes that isn't in the spec is dropped, not stored. This is
enforced in code and covered by automated tests, not just a prompt instruction.

## 12. What about citizens without smartphones or reliable internet?

Out of scope for this MVP pilot by design — PROJECT.md scopes M1 to a website (text + in-browser
voice). WhatsApp/USSD/call-based channels are explicitly roadmap, reusing the same backend engine
rather than starting over.

## 13. How do you prevent duplicate complaints or spam submissions?

Every message carries a client-generated `message_id`; a repeated one returns the original stored
response unchanged instead of re-running the AI or creating a second ticket — this is enforced by a
database primary key, not just application logic, so it holds even under network retries or
double-taps.

## 14. What's the officer's workflow — does this add burden to staff?

Officers see tickets already classified with a department, office, and citizen-language summary,
not a raw transcript to interpret. They can update status, reassign, and use a review queue for
low-confidence tickets — the goal is less manual triage, not more.

## 15. How do you know this actually reduces resolution time, not just intake?

Honestly: we don't have measured resolution-time numbers yet — that requires real usage over time,
not something a hackathon pilot can produce. What we can show today is fewer steps and less
required knowledge to *file* a complaint correctly; resolution-time impact is a claim for the
pilot-scale phase, not this submission.
