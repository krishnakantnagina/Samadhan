# SAMADHAN — TICKETS.md

Owners: **L** = Lead, **D** = Dev. Rule: start a ticket only when all dependencies are Done.
Status: Todo → In progress → In review → Done (or Blocked).

## Phase 0 — Setup, contracts, confirmations (27 Sep)
| ID | Ticket | Owner | Depends on | Done when | Status |
|---|---|---|---|---|---|
| T00 | Confirm PS5 registered, team size matches registration, portal format + exact cutoff time | L | — | All 3 confirmed | Todo |
| T01 | Repo, folders, `CLAUDE.md`, `.gitignore`, `.env.example`, branch protection | L | — | Dev cloned | Todo |
| T02 | API contract: `POST /message`, `GET /status/{complaint_id}` | L | — | Pydantic file merged | Todo |
| T03 | DB schema incl. `offices`, statuses, `SMD-` prefix | L | — | SQL merged | Todo |
| T04 | `water_supply.yaml` spec | L | — | Loads cleanly | Todo |
| T05 | Office data: 5 Bhopal wards + district fallback | L | T03 | Rows ready | Todo |
| T06 | Supabase: schema, `audio` bucket, offices, share keys | L | T03, T05 | Tables visible | Todo |
| T07 | FastAPI skeleton, config, CORS, `/health` | D | T01, T02 | 200 OK | Todo |
| T08 | Mock `/message` + `/status` | D | T07 | Callable from browser | Todo |
| T09 | 15 test sentences + 3 voice samples | L | — | Shared | Todo |
| T10 | Screenshots: CM Helpline menu bot (evidence) | L | — | 5 saved | Todo |

## Phase 1 — Core text flow (27–28 Sep)
| ID | Ticket | Owner | Depends on | Done when | Status |
|---|---|---|---|---|---|
| T11 | Spec loader | D | T04, T07 | Spec by ID | Todo |
| T12 | Turn Engine (Groq JSON + Gemini fallback) | D | T02, T11 | Valid JSON | Todo |
| T13 | Prompt tests | D | T09, T12 | ≥ 13/15 | Todo |
| T14 | Session manager | D | T06, T07 | Users isolated | Todo |
| T15 | Validator + confirmation | D | T11, T12, T14 | No invalid tickets | Todo |
| T16 | Jurisdiction resolver | D | T05, T06 | Correct ward | Todo |
| T17 | Ticket + routing (`needs_review` < 0.7) | D | T15, T16 | `SMD-` ticket with office | Todo |
| T18 | Real `/message` | D | T14–T17 | Text → ticket | Todo |
| T19 | Real `/status/{id}` | D | T17 | Correct status | Todo |
| T20 | Seed 15 tickets | L | T06 | Rows visible | Todo |
| T21 | Website chatbot UI (mobile, Hindi-first) | L | T08 | Works on mock | Todo |
| T22 | Status-check page | **D** | T08, T21 | Shows status | Todo |
| T23 | Dashboard: login, list, filters | L | T20 | Tickets listed | Todo |
| T24 | Dashboard: detail, status, reassign, review queue | L | T23 | Saves to DB | Todo |
| T25 | Backup video (text flow) | L | T18, T21, T23 | Recorded 28 Sep night | Todo |

🚦 Gate 28 Sep night: text complaint → ticket on dashboard.

## Phase 2 — Voice, integration, deploy (29 Sep)
| ID | Ticket | Owner | Depends on | Done when | Status |
|---|---|---|---|---|---|
| T26 | Voice: upload → FFmpeg → Sarvam → storage | D | T18 | Voice flow works | Todo |
| T27 | Fallbacks + timeouts | D | T26 | Survives 1 API down | Todo |
| T28 | `cancel` / `restart` / timeout | D | T18 | All work | Todo |
| T29 | Mic + location in UI | L | T21 | Audio + GPS reach API | Todo |
| T30 | Dashboard map | **D** | T24 | Pins show | Todo |
| T31 | Integration + 10 MVP scenarios | L | T19, T22, T24, T26, T29 | 10/10 pass | Todo |
| T32 | Deploy + local laptop run verified; tag `v1-mvp` | L | T31 | URLs + local both work | Todo |

## Phase 3 — Submission documents (draft 28 Sep, final 29 Sep)
| ID | Item | Owner | Depends on | Done when | Status |
|---|---|---|---|---|---|
| T33 | 1 · Solution synopsis / executive summary (1 page) | L | — | Final | Todo |
| T34 | 3 · Problem statement & proposed solution (with MP evidence) | L | T10 | Final | Todo |
| T35 | 4 · Innovation & differentiation note | L | — | Final | Todo |
| T36 | 5 · Impact & benefits (numbers: taps, typing, routing) | L | — | Final | Todo |
| T37 | 6 · Implementation / feasibility plan (pilot → MP scale) | L | — | Final | Todo |
| T38 | 7 · Technology architecture + security + scalability | D drafts, L reviews | T32 | Final | Todo |
| T39 | 10 · Why should this solution be selected | L | T33–T37 | Final | Todo |
| T40 | README + **attribution** (all libraries/APIs/templates) | D drafts, L reviews | T32 | Fresh-clone setup works | Todo |
| T41 | 8 · Demo video (2–3 min) + live URL | L | T32 | Uploaded | Todo |
| T42 | 2 · Presentation PDF (≤ 10 slides, 5–10 min pitch) | L | T33–T39, T41 | Final | Todo |
| T43 | **Submit all items** (9 · repo URL included) | L | T33–T42 | Done by 30 Sep noon | Todo |

## Phase 4 — Event prep, no product changes (1–8 Oct)
| ID | Ticket | Owner | Done when | Status |
|---|---|---|---|---|
| T44 | Pitch script (5–10 min), mapped to rubric weights | L | Timed | Todo |
| T45 | Jury Q&A bank (security, scale, cost, MPOnline integration, AI errors) | L + D | 20 answers | Todo |
| T46 | Code walkthrough: each member explains every module | L + D | Both can explain | Todo |
| T47 | Laptop demo kit: local run, hotspot, backup video, charged devices | L | Tested offline-safe | Todo |
| T48 | Rehearsal × 3 (incl. one with demo failure drill) | L + D | Done by 8 Oct | Todo |
| T49 | Event checklist: IDs with DOB, confirmation email, chargers | L | Packed | Todo |

## Queues
| Person | Order |
|---|---|
| Dev | T07 → T08 → T11 → T12 → T14 → T13 → T15 → T16 → T17 → T18 → T19 → T22 → T26 → T27 → T28 → T30 → T38 → T40 |
| Lead | T00 → T01 → T02 → T03 → T04 → T09 → T05 → T06 → T10 → T20 → T21 → T23 → T24 → T25 → T33–T37 (drafts) → T29 → T31 → T32 → T39 → T41 → T42 → T43 |
