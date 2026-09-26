# Plan: Deliver the S01 API Contract (`docs/contracts/API_SPEC.md`)

> **Update (27 Sep):** we dropped the contract freeze, the `contract-v1.0.0` tag, the changelog/gaps requirement and the Lead sign-off (see `PROJECT.md` §15 "Working Together"). Read Phase 3 and the Sign-off section as optional. The build work (`api.py`, mock, contract tests) is unchanged.

## Context

`docs/contracts/API_SPEC.md` (S01, v1, Draft) now defines the contract between the citizen website and the FastAPI core. On its own it is a document. Nothing yet enforces it: `docs/contracts/api.py` is empty, there is no mock, no contract tests, and the open items are not logged. PROJECT.md §5 and D8 require the contract **frozen on 27 Sep** so the Lead (website) and Dev (`/backend`) can work in parallel, and code freezes at the 30 Sep noon submission.

This plan turns the spec into a frozen, testable contract. It is saved in the repo as a real engineering plan so it can be reviewed, tracked and referenced from tickets.

## Where the plan is saved (on approval)

- New folder: `docs/plans/`
- File: `docs/plans/S01-api-contract-plan.md` (this document, same content)
- Convention for later plans: `docs/plans/<spec-id>-<slug>-plan.md`, sections in the order used below (Context → Goals → Deliverables → Work breakdown → Timeline → Risks → Decisions → Verification → Sign-off).
- Not committed until you ask.

## Goals

1. Freeze S01 as `v1.0.0` on 27 Sep.
2. Ship `api.py` as the single source of the request/response models.
3. Give Dev and the website a working mock on day 1.
4. Prove mock and real API behave the same via one shared contract test suite.

## Non-goals

Auth/OTP, rate limiting, WhatsApp, dashboard endpoints, TTS audio (all out of scope in S01 §14). Real Turn Engine, ASR and routing logic (S05 and others).

## Deliverables

| # | Deliverable | Location | Owner |
|---|---|---|---|
| D1 | Contract models | `docs/contracts/api.py` | Lead |
| D2 | Gaps logged | `docs/GAPS.md` | Lead |
| D3 | Changelog entry `v1.0.0` | `docs/CONTRACT_CHANGELOG.md` | Lead |
| D4 | PROJECT.md aligned with S01 | `docs/PROJECT.md` §8, §13 | Lead |
| D5 | Mock API (T08) | `backend/mock/` | Dev |
| D6 | Contract test suite | `backend/tests/contract/` | Dev |
| D7 | `ALLOWED_ORIGINS` documented | `.env.example` | Lead |
| D8 | Tag `contract-v1.0.0` | git tag | Lead |

## Work breakdown

**Phase 0 — Decisions (Lead, 27 Sep morning).** Close the items that block the freeze:
- G-API-1: confirm audio limits (≤ 60 s, ≤ 2 MB).
- G-API-2: confirm location-only turns (D-A8) and `mp4` audio (D-A9).
- Decide how to resolve the deviations in S01 §13 (update PROJECT.md, or revert S01): paths `/api/v1/...`, `updated_at`.
- Reconcile team roles: PROJECT.md §14 says Lead + one Dev, but `CLAUDE.md` says Dev A / Dev B.

**Phase 1 — Contract artifacts (Lead, 27 Sep).**
1. W1 — Write `api.py` from S01 Appendix A. Use the existing sketch: `ComplaintStatus`, `Action`, `OfficeLevel`, `ErrorCode`, `MessageRequest`, `Office`, `Ticket`, `MessageResponse`, `StatusResponse`, `HealthResponse`, `ErrorResponse`. Each model gets a docstring citing the S01 section.
2. W2 — Copy the 7 open items (G-API-1…7) into `docs/GAPS.md` with owner and needed-by date.
3. W3 — Add the `v1.0.0` entry to `docs/CONTRACT_CHANGELOG.md`.
4. W4 — Update PROJECT.md §8 and §13 per the Phase 0 decision.
5. W5 — Add `ALLOWED_ORIGINS=` to `.env.example`.
6. W6 — Start `specs/water_supply.yaml`. It is empty today and blocks the `summary` keys and the Turn Engine (G-API-6). Tracked as its own ticket, listed here only because it gates S01 examples.

**Phase 2 — Mock and contract tests (Dev, 27–28 Sep).**
1. W7 — Mock API (T08): FastAPI app importing `api.py`. Returns schema-valid canned responses for every `action` value, dedupes on `message_id` (sets `duplicate = true`), and serves `/health`.
2. W8 — Contract suite (pytest + httpx), driven by a `BASE_URL` env var so the same tests run against the mock and the real API. Covers:
   - the 9 checks in S01 §10.1;
   - the 10 scenarios in §10.2 as far as the mock can express them;
   - error bodies (`error_code`, `message`, `reply_text`, `request_id`);
   - a test that every JSON example in `API_SPEC.md` validates against the `api.py` models.
3. W9 — Override FastAPI's default `422` handler so validation errors return `400 INVALID_INPUT`.

**Phase 3 — Review and freeze (Lead + Dev, 27 Sep end of day).**
1. Dev reads S01 and `api.py` cold and confirms nothing needs a question.
2. Website side confirms it can build a chat screen from the response fields alone.
3. Lead tags `contract-v1.0.0` and posts the changelog line.

**Phase 4 — Integration (27–29 Sep).** Website develops against the mock; the real `/message` (T-series backend tickets) must pass the same contract suite before integration. Any contract change after the freeze follows S01 §9 rule 7 (Lead approves → version bump → changelog → mock update).

## Timeline

| Date | Milestone | Gate |
|---|---|---|
| 27 Sep | Phase 0 decisions; Phase 1 artifacts; mock started | `api.py` merged; contract frozen and tagged |
| 28 Sep | Mock + contract suite complete; website builds on mock | Suite green on mock |
| 29 Sep | Real backend passes the same suite; deploy; `ALLOWED_ORIGINS` set | Suite green on real API; 10/10 scenarios (PROJECT.md §17) |
| 30 Sep noon | Submission | Contract unchanged since `v1.0.0` (or every change logged) |

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `water_supply.yaml` not written | `summary` keys and Turn Engine blocked | Start W6 on 27 Sep; keep S01 examples marked illustrative |
| Contract churn after freeze | Website and backend drift | Lead-only changes, changelog, mock updated first |
| Safari audio (`mp4`) fails FFmpeg conversion | Voice broken on iPhone | Include an `mp4` sample in the contract suite |
| ASR + LLM latency ~14 s before fallback | Website feels frozen | Resolve G-API-4 (client timeout, loading UX) by 28 Sep |
| Concurrent duplicate `message_id` creates two tickets | Duplicate complaints | Unique `(session_id, message_id)` constraint in `db.sql`; test it |
| CORS misconfigured at deploy | Website blocked in prod | `ALLOWED_ORIGINS` documented (W5), CORS test in the suite |
| Deviations from PROJECT.md left unresolved | Conflicting sources of truth | Phase 0 decision + W4 |

## Open decisions for the Lead

1. Update PROJECT.md to match S01 (paths, `updated_at`), or revert S01? Plan assumes **update PROJECT.md**.
2. Confirm audio limits, location-only turns, `mp4` (G-API-1, G-API-2).
3. Show `needs_review` to citizens on the status endpoint, or map it? (G-API-3; default: return as-is.)
4. Team roles: Lead + Dev (PROJECT.md) or Dev A / Dev B (`CLAUDE.md`)?

## Verification

1. `python -c "import api"` from `docs/contracts/` — models import cleanly on Python 3.12.
2. Run the contract suite against the mock (`BASE_URL=http://localhost:8000 pytest backend/tests/contract`) — all green, including a valid response for each of the 6 `action` values.
3. Run the same suite against the real backend once `/api/v1/message` exists — identical results.
4. Example check: every JSON block in `API_SPEC.md` parses against its `api.py` model.
5. Manual scenario pass (PROJECT.md §17) from the website: text, Hindi voice, GPS, cancel, unknown location, two browsers.
6. Review: `git diff` shows `API_SPEC.md`, `api.py`, `GAPS.md`, `CONTRACT_CHANGELOG.md` changed together (S01 §9 rule 7).

## Sign-off

- Lead: approves contract and tag.
- Dev: confirms buildable without questions; owns mock and suite.
- Definition of done: S01 §10 acceptance all green on mock and real API, `contract-v1.0.0` tagged, open items either closed or logged in `GAPS.md`.

## Progress (27 Sep)

| Item | Status |
|---|---|
| W1 `api.py` | Done: models, limits, error tables, shared helpers |
| W2 `GAPS.md` | Done: G-API-1…8 and G-PROJ-1 (team roles) |
| W3 `CONTRACT_CHANGELOG.md` | Done: `v1.0.0`, marked pending freeze |
| W4 `PROJECT.md` | Done, using the plan's default (update PROJECT.md to match S01) |
| W5 `.env.example` | Done: `ALLOWED_ORIGINS` |
| W6 `water_supply.yaml` | Skeleton only; fields TBD (G-API-6) |
| W7 Mock API | Done: `backend/mock/` |
| W8 Contract suite | Done: 78 tests green on the mock, in-process and over HTTP |
| W9 `422` → `400` handler | Done: `backend/mock/errors.py` (real backend should reuse it) |
| Phase 3 freeze | Dropped: no freeze or tag; the Phase 0 questions are just chat decisions |
| Phase 4 integration | Pending: real `/api/v1/message` must pass the suite with `CONTRACT_TARGET=real` |
