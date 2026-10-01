# Implementation and Feasibility Plan

**Samadhan (समाधान): from a Bhopal pilot to Madhya Pradesh**

## 1. Feasibility today (what is running)
The prototype is built and tested: a FastAPI core, a website with voice and GPS, a Supabase database with a private audio bucket, and a
Streamlit officer dashboard. It runs five services (water, electricity, roads, sanitation, general triage) on one engine. Everything used is
on free tiers, and everything server-side is stateless except the database.

## 2. Phased plan

| Phase | Goal | Work | Depends on | Exit check |
|---|---|---|---|---|
| **0. Prototype (done)** | Prove the flow | Website chat, voice, routing, tickets, dashboard, status | none | Ten scenarios exercised; 415 + 35 tests pass |
| **1. Make the data real** | Replace demo data | Verified ward and office data for Bhopal (RTI or a visit to BMC); ward centre points from the ward boundary file; officer roles; resolve BMC-versus-PHED ownership | BMC cooperation | GPS picks the correct ward; no `(DEMO)` rows in the pilot |
| **2. Harden for real users** | Safe to open to the public | Phone-verified complaints (SMS OTP); rate limits on `/message` and `/speak`; per-department officer accounts; officer notification when a ticket arrives; retention policy and consent notice | Phase 1 | Abuse test passes; officers see only their department |
| **3. Pilot in Bhopal** | Measure real impact | Live pilot with a few wards, then all Bhopal wards; track reassignments, time to first status change and voice use | Phase 2 | The four impact metrics in item 05 have real numbers |
| **4. Add departments and districts** | Scale across MP | One YAML service spec plus office rows per department; a central department registry file with checks; another city as a second pilot | Phase 3 | A new department goes live with no engine code change |
| **5. Integrate** | Fit the existing ecosystem | Ticket hand-off to MPOnline's Customer Solutions Hub / CM Helpline; WhatsApp channel on the same engine; DigiLocker-based document help with citizen consent | MPOnline agreement | Tickets land in the existing system |

Phase order matters: phone verification and rate limiting come before any public launch, because an open SMS endpoint costs money per
message and invites fake complaints.

## 3. Resources and cost (indicative, to be confirmed)
| Item | Today | At pilot scale |
|---|---|---|
| LLM (Groq free tier, Gemini fallback) | Free; Groq free tier is about 8,000 tokens per minute per model, so bursts can exhaust it | Paid tier |
| Speech (Sarvam) | Free tier | Paid, per use |
| Database and storage (Supabase) | Free; can pause after 7 days of inactivity | Paid plan |
| Hosting (Railway or Render, Vercel, Streamlit Community Cloud) | Free; free hosts sleep when idle | Paid plan |
| SMS OTP for phone verification | Not in the product; one test succeeded | Per-message cost; Indian SMS needs DLT (sender and template) registration, which takes days |
| Exact figures | TBD | TBD |

## 4. Risks and how we handle them
| Risk | Mitigation |
|---|---|
| AI misroutes a complaint | Validator against the spec; confidence threshold; `needs_review`; officer reassign with a logged correction |
| Provider outage or rate limit | LLM chain of four models; ASR fallback; short timeouts; Hindi error messages |
| Spam or fake complaints | Phase 2: phone verification, rate limits, duplicate detection |
| Wrong or unverified office data | Verified-or-labelled rule: every unverified row is marked DEMO; a registry with source and verified fields is proposed |
| Privacy and DPDP Act compliance | Minimal data by design; a full review (consent, retention, grievance officer) is a Phase 2 task, and we do not claim compliance today |
| Free tier limits | Move to paid plans before any public pilot |

## 5. Team and process
A two-person team, working spec-first: every module has a written spec (`docs/specs/S01 to S31`) and plan before code. The repository
holds the specs, tickets and research so a new developer can pick it up (`docs/ONBOARDING.md`).
