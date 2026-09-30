# SAMADHAN — TICKETS.md

Owners: **L** = Lead, **D** = Dev: who usually does it; either of us can pick up any ticket.
"Depends on" is a suggested order, not a rule. Tick `[x]` when done.

## Phase 0 — Setup, contracts, confirmations (27 Sep)
| ID | Ticket | Owner | Depends on | Done when | Done |
|---|---|---|---|---|---|
| T00 | Confirm PS5 registered, team size matches registration, portal format + exact cutoff time | L | — | All 3 confirmed | [ ] |
| T01 | Repo, folders, `CLAUDE.md`, `.gitignore`, `.env.example` | L | — | Dev cloned | [ ] |
| T02 | API contract (`docs/specs/S01-api-contract.md`, `backend/app/schemas.py`): `POST /api/v1/message`, `GET /api/v1/status/{complaint_id}`, `/health` | L | — | Pydantic file pushed | [x] |
| T03 | DB schema incl. `offices`, statuses, `SMD-` prefix | L | — | SQL pushed | [x] |
| T04 | `water_supply.yaml` spec | L | — | Loads cleanly | [x] |
| T05 | Office data: 5 Bhopal wards + district fallback | L | T03 | Rows ready | [x] |
| T06 | Supabase: schema, `audio` bucket, offices, share keys | L | T03, T05 | Tables visible | [x] |
| T07 | FastAPI skeleton, config, CORS, `/health` | D | T01, T02 | 200 OK | [x] |
| T08 | Mock `/message` + `/status` | D | T07 | Callable from browser | [x] |
| T09 | 15 test sentences + 3 voice samples | L | — | Shared | [x] |
| T10 | Screenshots: CM Helpline menu bot (evidence) | L | — | 5 saved | [ ] |

## Phase 1 — Core text flow (27–28 Sep)
| ID | Ticket | Owner | Depends on | Done when | Done |
|---|---|---|---|---|---|
| T11 | Spec loader | D | T04, T07 | Spec by ID | [x] |
| T12 | Turn Engine (Groq JSON + Gemini fallback) | D | T02, T11 | Valid JSON | [x] |
| T13 | Prompt tests | D | T09, T12 | ≥ 13/15 | [ ] |
| T14 | Session manager | D | T06, T07 | Users isolated | [x] |
| T15 | Validator + confirmation | D | T11, T12, T14 | No invalid tickets | [x] |
| T16 | Jurisdiction resolver | D | T05, T06 | Correct ward | [x] |
| T17 | Ticket + routing (`needs_review` < 0.7) | D | T15, T16 | `SMD-` ticket with office | [x] |
| T18 | Real `/message` | D | T14–T17 | Text → ticket | [x] |
| T19 | Real `/status/{id}` | D | T17 | Correct status | [x] |
| T20 | Seed 15 tickets | L | T06 | Rows visible | [x] |
| T21 | Website chatbot UI (mobile, Hindi-first) | L | T08 | Works on mock | [x] |
| T22 | Status-check page | **D** | T08, T21 | Shows status | [x] |
| T23 | Dashboard: login, list, filters | L | T20 | Tickets listed | [x] |
| T24 | Dashboard: detail, status, reassign, review queue | L | T23 | Saves to DB | [x] |
| T25 | Backup video (text flow) | L | T18, T21, T23 | Recorded 28 Sep night | [ ] |

🚦 Target 28 Sep night: text complaint → ticket on dashboard.

## Phase 2 — Voice, integration, deploy (29 Sep)
| ID | Ticket | Owner | Depends on | Done when | Done |
|---|---|---|---|---|---|
| T26 | Voice: upload → Sarvam/Groq Whisper (no FFmpeg, S12 D-S12-1) → storage | D | T18 | Voice flow works | [x] |
| T27 | Fallbacks + timeouts | D | T26 | Survives 1 API down | [x] |
| T28 | `cancel` / `restart` / timeout | D | T18 | All work | [ ] |
| T29 | Mic + location in UI | L | T21 | Audio + GPS reach API | [x] |
| T30 | Dashboard map | **D** | T24 | Pins show | [ ] |
| T31 | Integration + 10 MVP scenarios | L | T19, T22, T24, T26, T29 | 10/10 pass | [ ] |
| T32 | Deploy + local laptop run verified | L | T31 | URLs + local both work | [ ] |
| T50 | Bug: `app.js` shows raw browser error instead of Hindi fallback on network failure (see `docs/problems/T50-app-js-network-fallback.md`) | D | T21 | Backend unreachable → Hindi message shown, not raw error | [x] |
| T51 | TTS voice reply (Sarvam Bulbul), speaker button on bot messages | D backend, L frontend | T26 | Speaker button plays a real Hindi reply | [x] |
| T52 | Citizen website redesign for villagers: WhatsApp-style press-and-hold mic, new greeting copy (see `docs/T52-designer-brief.md`) | New UI/UX+dev hire | T29, T51 | Brief's own Acceptance checklist, all boxes | [ ] |
| T53 | Floating chat widget (real, text-only) for pages without the full chat (see `docs/specs/S19-chat-widget.md`) | D | S01, T22 | Real widget opens/closes, sends/receives real messages on `status.html` | [x] |

## Phase 3 — Submission documents (draft 28 Sep, final 29 Sep)
| ID | Item | Owner | Depends on | Done when | Done |
|---|---|---|---|---|---|
| T33 | 1 · Solution synopsis / executive summary (1 page) | L | — | Final | [ ] |
| T34 | 3 · Problem statement & proposed solution (with MP evidence) | L | T10 | Final | [ ] |
| T35 | 4 · Innovation & differentiation note | L | — | Final | [ ] |
| T36 | 5 · Impact & benefits (numbers: taps, typing, routing) | L | — | Final | [ ] |
| T37 | 6 · Implementation / feasibility plan (pilot → MP scale) | L | — | Final | [ ] |
| T38 | 7 · Technology architecture + security + scalability | D drafts, L reviews | T32 | Final | [ ] |
| T39 | 10 · Why should this solution be selected | L | T33–T37 | Final | [ ] |
| T40 | README + **attribution** (all libraries/APIs/templates) | D drafts, L reviews | T32 | Fresh-clone setup works | [ ] |
| T41 | 8 · Demo video (2–3 min) + live URL | L | T32 | Uploaded | [ ] |
| T42 | 2 · Presentation PDF (≤ 10 slides, 5–10 min pitch) | L | T33–T39, T41 | Final | [ ] |
| T43 | **Submit all items** (9 · repo URL included) + tag `v1-mvp` | L | T33–T42 | Done by 30 Sep noon | [ ] |

## Phase 4 — Event prep, no product changes (1–8 Oct)
| ID | Ticket | Owner | Done when | Done |
|---|---|---|---|---|
| T44 | Pitch script (5–10 min), mapped to rubric weights | L | Timed | [ ] |
| T45 | Jury Q&A bank (security, scale, cost, MPOnline integration, AI errors) | L + D | 20 answers | [ ] |
| T46 | Code walkthrough: each member explains every module | L + D | Both can explain | [ ] |
| T47 | Laptop demo kit: local run, hotspot, backup video, charged devices | L | Tested offline-safe | [ ] |
| T48 | Rehearsal × 3 (incl. one with demo failure drill) | L + D | Done by 8 Oct | [ ] |
| T49 | Event checklist: IDs with DOB, confirmation email, chargers | L | Packed | [ ] |

## Suggested order (not a rule)
| Person | Order |
|---|---|
| Dev | T07 → T08 → T11 → T12 → T14 → T13 → T15 → T16 → T17 → T18 → T19 → T22 → T26 → T27 → T28 → T30 → T38 → T40 |
| Lead | T00 → T01 → T02 → T03 → T04 → T09 → T05 → T06 → T10 → T20 → T21 → T23 → T24 → T25 → T33–T37 (drafts) → T29 → T31 → T32 → T39 → T41 → T42 → T43 |

## Status notes (verified 29 Sep 2026)

Ticked today, each checked before ticking:
- **T02** `S01-api-contract.md` + `backend/app/schemas.py` exist. The shared contract suite passes against the mock (88 passed)
  and against the **real** backend with real Groq/Supabase (68 passed, 20 `mock_only` skipped; needs
  `CONTRACT_EXISTING_ID=SMD-0001`, because the default `SMD-0042` only exists in the mock).
- **T04** `specs/water_supply.yaml` loads (`water_supply`, Jal Vibhag, 4 fields) on every backend start.
- **T08** the mock runs (`uvicorn mock.app:app --port 8001`), answers `/health` and `POST /api/v1/message` over HTTP, and the
  citizen website was built against it.

Left unticked, on purpose:
- **T01** repo, folders, `CLAUDE.md`, `.gitignore`, `.env.example` all exist, but "Dev cloned" cannot be verified from the repo
  (all 50 commits are by one author). Tick it when the Dev confirms.
- **T00, T10, T25** need the Lead (confirmations, CM Helpline screenshots, backup video). Nothing in the repo can show them done.
- **T13** prompt tests: 6 live runs, 11 / 10 / 9 / 9 / **13** / **12** of 15 (`submission/T13-prompt-test-results-run*.json`,
  analysis in `docs/specs/S21` and `S27`). Target met once, missed once. Remaining misses: two vague sentences and the drainage
  sentence, which flips between pass and fail. Left open rather than ticked on the lucky run.
- **T28** typed `cancel` / `restart` / timeout verified live (S20 L1, L2, L4, L5) and spoken commands are implemented and unit
  tested. Open: **L3** (session reuse after a submitted ticket, needs a real ticket) and **L6** (a real spoken cancel/restart
  through Sarvam, needs a human at the mic).
- **T30** map built and tested (`docs/specs/S24`): 25 dashboard tests; the real app run against live data showed 3 tabs, 2 pins,
  18 tickets without GPS. Open: not yet looked at in a real browser (tiles, filters, the "Open ticket" picker).
- **T31** 10-scenario pass: not done.
- **T32** deploy config is ready (`Dockerfile`, `vercel.json`, `docs/DEPLOY.md`, spec `S22`); nothing is deployed yet and the
  Docker image was never built (no Docker on the dev machine).
- **S31 (30 Sep)**: home page is the hero only; chat opens as the widget from the hero mic; greeting plays `frontend/greeting-hi.wav` (no TTS). Restore point: tag `checkpoint-before-hero-widget`.
- **T52** unchanged: 2 of 7 checklist items still need a human (real Android device, a spoken test through the press-and-hold mic).
- **T33-T43** (submission documents, demo video, slides, submit + tag `v1-mvp`) and **T44-T49** (event prep) not started.

Unticketed work done since 28 Sep, for the record: T09 (ticked above), warm replies (`S25`), Groq model fallback chain
(`S26`), generic-place guard (`S27`), location yes/no chips and the `sessions.service_id` fix (`S23`), voice-note bubbles and
auto-speak (`S17` D-S17-4/5), auto-scroll from the hero page.

### Added 29 Sep (evening): multi-department routing, S28
Approved by the Lead and built: electricity, roads, sanitation and a general-triage service besides water; a message-kind step
(complaint / information / out of context) with fixed replies and a validated `.gov.in` link plus disclaimer; clarify / reconfirm
questions; dashboard cross-department reassign. Spec `docs/specs/S28`, live results and caveats in its BUILD LOG. Measured routing
accuracy about 90% on 60 messages (synthetic data caveat). Groq free-tier capacity (8,000 tokens per minute per model) is the main
demo risk. **T13 needs a new baseline** (it was written for a one-service bot). Restore point before this work: git tag
`checkpoint-before-multidept`.
