# SAMADHAN — PROJECT.md

> **Single source of truth** for the team lead, developer, and AI coding agents.
> Product, milestones, and delivery plan are one project. Contracts, schema, specs, and tickets live in other files (see [§22](#22-related-files--submission-items)).
>
> **Unknown items are `TBD`: never guess; log a spec gap in `docs/GAPS.md`.**

## Contents

1. [Purpose, Track & Positioning](#1-purpose-track--positioning)
2. [Problem (evidence for judges)](#2-problem-evidence-for-judges)
3. [Users](#3-users)
4. [Goals — Scored Against the Official Rubric](#4-goals--scored-against-the-official-rubric-technical-track)
5. [Timeline, Milestones & Gates](#5-timeline-milestones--gates)
6. [Scope](#6-scope)
7. [End-to-End Workflow](#7-end-to-end-workflow)
8. [Architecture](#8-architecture)
9. [Routing & Jurisdiction](#9-routing--jurisdiction)
10. [AI Responsibilities & Boundaries](#10-ai-responsibilities--boundaries)
11. [Tech Stack & Attribution](#11-tech-stack--attribution)
12. [External Dependencies](#12-external-dependencies)
13. [Security & Privacy](#13-security--privacy)
14. [Team & Ownership](#14-team--ownership)
15. [Development Pipeline](#15-development-pipeline)
16. [Critical Path](#16-critical-path)
17. [MVP Acceptance Gate](#17-mvp-acceptance-gate-before-recording-and-submission)
18. [Risks & Mitigations](#18-risks--mitigations)
19. [Lead Reminders — Never Lose](#19-lead-reminders--never-lose)
20. [Decision Log](#20-decision-log)
21. [Defaults vs Open Items](#21-defaults-vs-open-items)
22. [Related Files & Submission Items](#22-related-files--submission-items)

---

## 1. Purpose, Track & Positioning

Samadhan is a multilingual, voice-first **AI chatbot website** for citizen grievances.

- Citizens speak or type (Hindi / Hinglish).
- The AI collects missing details, validates them, creates a ticket, routes it to the correct department **and ward office**, and returns a complaint ID for status checks.
- Officers work tickets on a dashboard.

| | |
|---|---|
| **Event** | MPOnline Idea & Innovation Hackathon 2026, Bhopal. Organizer = MPOnline Limited. |
| **Track** | Problem Statement 5 — AI Innovation for Public Services & Citizen-Centric Governance (explicitly lists citizen grievance redressal, voice bots, conversational AI). Track locked after submission. |
| **Positioning** | The AI front door that feeds MPOnline / MP grievance systems. Complements, never replaces. Frame gaps respectfully (e.g. "extends the Customer Solutions Hub multilingual roadmap to citizen channels"). |

## 2. Problem (evidence for judges)

| Existing channel (MP) | Gap Samadhan fills |
|---|---|
| CM Helpline WhatsApp bot | Menu-driven (type option numbers); no free-form understanding |
| CM Helpline 181 call | Operator types complaint manually; fixed hours (7:30 AM–11 PM); queues |
| MPOnline Customer Solutions Hub | AI backend exists; multilingual on roadmap; AI not on citizen channels |
| Saarathi bot | Capabilities `TBD` (verify hands-on) |

**Core gaps:**

- Citizen must know the category/department.
- No free-form voice intake.
- Standard language assumed.
- Manual data entry.
- No visible status loop.

## 3. Users

| User | Needs |
|---|---|
| Citizen (urban + rural, low-literacy, mobile browser) | Speak/type in own language; few questions; complaint ID; status |
| Ward / department officer | Complete validated tickets; audio + transcript; location; status control |

## 4. Goals — Scored Against the Official Rubric (technical track)

| Criterion | Weight | How Samadhan wins it |
|---|---|---|
| Innovation & Originality | **20% (tie-breaker)** | Dialect voice → exact ward office; spec-driven AI that cannot invent departments |
| Prototype / MVP | **20%** | Live URL + laptop demo; 10/10 scenarios ([§17](#17-mvp-acceptance-gate-before-recording-and-submission)) |
| Problem Understanding | 15% | Real MP evidence: menu bot, 181 hours, manual entry |
| Technical Feasibility | 15% | Clear architecture, fallbacks, security, explainable code |
| Impact on Governance | 15% | 1 voice note vs 6+ taps; zero operator typing; right office first time |
| Scalability & Sustainability | 10% | YAML specs for new services; LGD data for statewide wards; one engine for WhatsApp/181 |
| Presentation & Demo | 5% | ≤10-slide deck, 5–10 min pitch, rehearsed |

> **~60% of the score is documents + pitch.** Documents are deliverables, not afterthoughts.

## 5. Timeline, Milestones & Gates

| Date | Milestone | Gate |
|---|---|---|
| 27 Sep | Setup, contracts frozen, mock API; confirm track + team registration + portal format | Dev building |
| 28 Sep | Text flow end to end; draft documents | Text complaint → ticket on dashboard; backup video |
| 29 Sep | Voice, location, integration, deploy, video; finish documents | 10/10 scenarios; tag `v1-mvp` |
| 30 Sep | **M1: submit all items by noon** | Submitted (late = not evaluated; exact cutoff `TBD`) |
| 1–8 Oct | **M2 prep:** pitch, Q&A, rehearsal, laptop demo setup — **no product changes** | 3 rehearsals done |
| 9 Oct | Semi-final: demo/presentation to jury (15 technical teams); 5 advance | Selected |
| 10 Oct | Finale: pitch on stage | Win |

> **Rule: no changes to the project after submission.** The 30 Sep version is the product judged.
> Finalists may refine the *presentation* after the Day 1 mentor briefing; the code stays `v1-mvp`.

## 6. Scope

### Current — M1 (submitted 30 Sep)

- Website chatbot: text + in-browser voice + location; mobile-responsive, Hindi-first.
- 1 service `water_supply` (Jal Vibhag). Pilot: **Bhopal, 5 wards** + district fallback office.
- Turn Engine, validation, confirmation, ticket `SMD-xxxx`, department + ward-office routing.
- Status check by complaint ID.
- Dashboard: login, list, detail, status, reassign, review queue, map.
- `cancel`, `restart`, 30-min timeout; ASR + LLM fallbacks.

### Future (roadmap slide only — not built before the event)

- TTS reply; phone OTP; status by verified mobile; more services and wards; KPI tiles.
- WhatsApp + 181 + Saarathi on the same engine; complaint clustering; CM Helpline/CSH API integration; ML routing from officer corrections; statewide LGD jurisdiction data.

### Out of Scope

- Any product change after 30 Sep; mobile app; replacing MPOnline systems; autonomous decisions.
- Unsupported services; self-hosted models, Redis, Celery, Kubernetes, microservices.

## 7. End-to-End Workflow

1. Citizen opens the website; voice/text (+ optional GPS) in the chatbot. Anonymous session.
2. Backend acknowledges; dedupes by `message_id`.
3. Voice → 16 kHz mono WAV → ASR. Original audio + transcript preserved.
4. Turn Engine (1 LLM call): service, fields, missing fields, action, reply, summary, confidence.
5. Backend validates against the spec; asks the next question or requests confirmation.
6. Jurisdiction resolver: location → ward → office for department + ward.
7. Ticket `SMD-xxxx` created. No ward match or confidence < 0.7 → district office + `needs_review`.
8. Citizen receives complaint ID + office.
9. Officer updates status / reassigns (logged in `routing_corrections`).
10. Citizen checks status by complaint ID (status + department only).

## 8. Architecture

```text
[Citizen] → [Website chatbot: chat | voice | location | status by complaint ID]
                                  |
          [FastAPI backend: API contract, sessions, dedupe, status lookup]
            |              |             |                |
      [Voice module]  [Turn Engine]  [Validator]  [Jurisdiction + ticket + router]
            |              |        (specs in memory)     |
      [Sarvam ASR]     [LLM API]                          | tickets, offices, status
            | audio                                       v
   [Supabase: Postgres (sessions, messages, tickets, offices, routing_corrections) + Storage + Auth]
                 | reads tickets                  ^ status updates, reassignments
                 v                                |
[Officer dashboard: login | list | detail (audio, transcript, summary) | status | reassign
                  | needs_review queue | map]  ← [Officer]
```

**Contracts** (Lead-owned, frozen 27 Sep): API (`/message`, `/status/{complaint_id}`) and DB schema.

- Website never touches the DB; dashboard never calls core.
- Statuses: `new`, `in_progress`, `resolved`, `needs_review`.
- Decisions: routing in core; dashboard displays stored data only; one LLM call per turn; specs loaded at startup.

## 9. Routing & Jurisdiction

- **Office = Department (service spec) + Jurisdiction (location).**
- Input: browser GPS or ward/village name extracted by the AI. Pilot: GPS → nearest ward; name → fuzzy match.
- Hierarchy:
  - Urban: Ward → Zone → Municipal Corp
  - Rural: Village → Gram Panchayat → Block → District
- `offices` table entered manually for the pilot. Scale-up sources: LGD codes; ward boundary GeoJSON.

## 10. AI Responsibilities & Boundaries

| Component | Does | Must NOT |
|---|---|---|
| LLM (Turn Engine) | Understand language, pick configured service, extract fields, next question, reply, summary, confidence | Invent services, fields, departments, offices, rules |
| Backend | Sessions, validation, confirmation gate, jurisdiction, tickets, routing, fallbacks | Trust LLM output unvalidated |
| Service spec (YAML) | Fields, rules, questions, department | — |
| Website | Capture input; show replies + status | Hold business logic; call LLM/ASR directly |

- Pydantic-validate all LLM output.
- Prompt = state + active spec + last ~4 messages.
- Timeouts: ASR ~8s, LLM ~6s.

## 11. Tech Stack & Attribution

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI (async), Uvicorn, Pydantic, httpx, PyYAML |
| Voice | FFmpeg; Sarvam Saarika ASR (fallback Groq Whisper) |
| LLM | Groq (Llama-class) primary, JSON mode; Gemini Flash fallback |
| Jurisdiction | rapidfuzz; lat/lng distance (pilot) |
| Data | Supabase Postgres, Storage, Auth |
| Website / Dashboard | HTML, CSS, JS, MediaRecorder, Geolocation / Streamlit, folium, pandas |
| Tooling | uv, Ruff, pytest, Git/GitHub, ngrok, Claude Code (AI assistant — permitted) |
| Hosting | Railway (API), Vercel (website), Streamlit Cloud; **event demo runs on own laptop** |

> **Attribution is mandatory:** every library, public API, and template must be listed in the README and submission.
> Both team members must be able to explain and demo all submitted code.

## 12. External Dependencies

| Dependency | Mitigation |
|---|---|
| Sarvam / Groq / Gemini | Cross-fallbacks; keys tested before demo |
| Supabase | Seed script to rebuild |
| Event Wi-Fi / free hosting | Local run on laptop; mobile hotspot backup; warm-up request |

## 13. Security & Privacy

- Secrets in `.env` only; service key backend-only; website holds no DB keys.
- HTTPS; CORS restricted to the website domain.
- Anonymous citizen sessions (verification method `TBD`).
- Complaint-ID lookup shows status + department only.
- Officer login; contact details masked.
- Original audio + transcript preserved.
- DPDP Act alignment; retention `TBD`.
- AI routes; officers decide.

## 14. Team & Ownership

| Role | Owns | Responsibilities |
|---|---|---|
| **Lead** | `/docs`, `/specs`, contracts, `/frontend`, `/dashboard` | Architecture, contracts, office data, website, dashboard core, integration, deploy, **all submission documents**, deck, video, submission |
| **Dev** | `/backend` (+ status page, map) | API, Turn Engine, voice, validation, jurisdiction, routing, tickets, fallbacks |

Registered team composition is locked by the organizer: **verify it matches the actual team** (`TBD`).

## 15. Development Pipeline

1. Read `PROJECT.md` → ticket → only the needed specs/contracts. Start only when dependencies are Done.
2. Contracts change only via Lead. Never invent business rules; log gaps in `GAPS.md`.
3. Branch per ticket; commit prefix = ticket ID; PR to protected `main`; Lead reviews within 1 hour.
4. Slash commands before submission: `/start`, `/done`, `/lead-review` only.
5. **No new features after 28 Sep night. Code frozen at submission; tag `v1-mvp`.**

## 16. Critical Path

Contracts → Turn Engine → Validator → Ticket/routing → real `/message` → Voice → Integration → Deploy → Video → Submission.

Documents run in parallel and must not slip past 29 Sep night.

## 17. MVP Acceptance Gate (before recording and submission)

| # | Scenario | Pass when |
|---|---|---|
| 1 | Hindi voice: "3 दिन से पानी नहीं आ रहा" | Asks only for location |
| 2 | Hinglish text | Same flow |
| 3 | All details in one message | Straight to confirmation |
| 4 | Correct a field at confirmation | Updates, no restart |
| 5 | `cancel` | Session cleared |
| 6 | Unrelated request | Polite out-of-scope; no invented service |
| 7 | GPS in pilot ward | Correct ward office |
| 8 | Unknown location | District office + `needs_review` |
| 9 | Officer sets "In progress" | Complaint-ID check shows it |
| 10 | Two browsers at once | Sessions never mix |

## 18. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Text flow late (28 Sep) | Cut map/commands first, never voice |
| Documents rushed | Draft on 28 Sep from this file; final on 29 Sep |
| Late submission | Submit by noon 30 Sep |
| Rule violation (post-submission changes, missing attribution) | Code freeze; attribution section |
| Demo failure at venue | Laptop local run, hotspot, backup video |
| Many PS5 grievance teams | Lead with originality: dialect → ward office |
| Team mismatch with registration | Confirm with organizer today |

## 19. Lead Reminders — Never Lose

- [ ] Always have something submittable: backup video after the text flow works.
- [ ] Every rubric point has an owner; ~60% of the score is documents + pitch.
- [ ] Judges are MPOnline: speak their language (CM Helpline, CSH, KPIs, Bhopal); respect their systems.
- [ ] Originality breaks ties: one unforgettable line — "Speak in your language; reach your ward office."
- [ ] Only claim what works; everything else is the roadmap.
- [ ] Tag before recording; freeze after submission; demo from your own laptop.
- [ ] Both members can explain every line of code.
- [ ] Unblock Dev first at every sync.

## 20. Decision Log

| # | Decision | Reason |
|---|---|---|
| D1 | Website chatbot is the product | No messaging setup; full UX control; demo link |
| D2 | WhatsApp/calls → roadmap | Same engine reusable |
| D3 | One LLM call per turn | Latency, cost, reliability |
| D4 | Front door to MPOnline/MP systems | Organizer runs CSH; gap is citizen channels |
| D5 | Routing in core: spec + jurisdiction + confidence | No labelled data |
| D6 | Officer reassignments logged | Future ML data |
| D7 | Groq primary, Gemini fallback; Streamlit dashboard | Speed of response and build |
| D8 | Contracts frozen Day 1, Lead-owned | Parallel work |
| D9 | `SMD-` DB-sequence IDs; complaint-ID status (status + dept) | No races; privacy |
| D10 | Bhopal 5-ward pilot, manual offices | Event city; data unavailable |
| D11 | Team = Lead + 1 Dev | Current team |
| D12 | Track = PS5 | Direct fit: grievance, voice bots, conversational AI |
| D13 | No product changes after 30 Sep; M2 = pitch only | Rule 2.1 / FAQ 16 |
| D14 | Documents are first-class deliverables | ~60% of rubric |
| D15 | Event demo runs locally on own laptop | SOP-04; venue network risk |

## 21. Defaults vs Open Items

| Item | Default now | Open (`TBD`) |
|---|---|---|
| Citizen verification | Anonymous session | OTP method; phone as `user_id` |
| Officer auth | Simple password | Per-department access |
| Dialects | Claim Hindi + Hinglish only | After ASR testing |
| Domain | Vercel subdomain | Custom domain |
| Submission | All 10 items ([§22](#22-related-files--submission-items)) | Portal format: separate files or one PDF; exact cutoff time |
| Other | — | Registered PS5 + team size confirmed; shortlist date; Saarathi; retention |

## 22. Related Files & Submission Items

### Related files

| File | Content |
|---|---|
| `CLAUDE.md`, `docs/TICKETS.md`, `docs/GAPS.md`, `docs/CONTRACT_CHANGELOG.md` | Rules, tickets, gaps, contract history |
| `docs/contracts/api.py`, `db.sql`, `specs/*.yaml` | API contract, DB schema, service specs |

### Submission items (`submission/`)

1. Synopsis
2. Presentation PDF (≤10 slides)
3. Problem & Solution
4. Innovation note
5. Impact
6. Feasibility plan
7. Architecture
8. Demo (live URL + video)
9. Repo URL
10. Why select us
