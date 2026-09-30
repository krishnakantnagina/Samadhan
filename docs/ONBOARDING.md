# Onboarding — start here

Welcome to Samadhan. This doc is a fast orientation for a new developer joining the team — what
the project is, what's actually built and working right now, how to run it, and where to look next.
It's a summary; the real source of truth is [`docs/PROJECT.md`](PROJECT.md), and this file will go
stale faster than that one, so when in doubt trust `docs/TICKETS.md` and the code over this page.

## What this is

A voice-first AI chatbot for citizen grievances in Madhya Pradesh: a citizen speaks or types
(Hindi/Hinglish) → the AI asks only for missing details → the citizen confirms → a ticket
(`SMD-xxxx`) is created and routed to the correct department + ward office → the citizen can check
status by complaint ID. Officers manage tickets on a dashboard. Built for the MPOnline Idea &
Innovation Hackathon 2026, Problem Statement 5, pilot scope: one service (`water_supply`), one city
(Bhopal, 5 wards + district fallback). **Submission deadline: 30 Sep, noon** (`docs/PROJECT.md` §1).

Two people: **Lead** (website, dashboard, data, submission docs) and **Dev** (backend, API,
integrations) — though in practice tickets get picked up by whoever's available; either can touch
any file, see [`CLAUDE.md`](../CLAUDE.md) for the working agreement.

## Read in this order

1. [`docs/PROJECT.md`](PROJECT.md) — the actual source of truth: scope, request flow, tech stack,
   rules, definition of done. Read this fully before touching anything.
2. [`docs/TICKETS.md`](TICKETS.md) — the checklist. Shows exactly what's done, what's not, and who
   usually owns what. **Trust this over this page** — it moves fast.
3. Whichever `docs/specs/S*.md` file owns the piece you're about to touch. **Every module in this
   project has a spec written before it was coded** — read the spec first, not just the code, since
   the spec carries the *why* behind decisions the code alone won't explain (see "How this was
   built" below).
4. The code itself.

## Current state (verified against `docs/TICKETS.md` on 29 Sep — check that file directly, this page will be stale again soon)

**Backend: fully built and live-verified**, T11–T27 + T51 — the entire text and voice complaint
flow, end to end, against real Groq/Gemini/Sarvam/Supabase, not just mocked: `POST
/api/v1/message` (text, voice, GPS-only), `GET /api/v1/status/{complaint_id}`, `POST
/api/v1/speak` (TTS reply, T51), spec-driven field extraction and validation, session management
with a 30-minute timeout, jurisdiction resolution (GPS or fuzzy ward-name match), ticket creation
with `needs_review` routing, provider fallbacks with sane timeouts everywhere. **A real, fully
voice-originated ticket has actually happened** — `SMD-0019`, a genuine human-spoken Hindi
conversation through issue → location → confirm → submitted (found via direct DB query while
verifying T52, documented in `docs/specs/S18-citizen-ui-redesign.md` G-S18-3).

**Frontend: three real surfaces, all live-verified against the real backend, not mocks:**
- `frontend/index.html` + `app.js` — the full citizen chat page (T21), now with press-and-hold
  voice (T29, redesigned in T52 to a WhatsApp-style hold gesture), GPS location, a 🔊 TTS speak
  button on every bot reply (T51), restart/cancel commands, and a delayed bilingual (Hindi +
  English) auto-playing greeting (T52). **T52 (the villager-first visual redesign) is not fully
  closed** — its own Acceptance checklist in `docs/T52-designer-brief.md` has 2 of 7 boxes still
  open: real Android-device testing, and a human speaking through the *new* press-and-hold gesture
  specifically (the underlying pipeline is proven via `SMD-0019`, just not through this exact new
  button yet). Both need a human, not more engineering.
- `frontend/status.html` + `status.js` — read-only status lookup by complaint ID (T22).
- `frontend/widget.js` — a floating chat widget (T53), added to `status.html` only (not
  `index.html`, which is already the full chat). As of the same-day revision, it has **full
  functional parity** with `app.js` — voice, location, TTS, restart/cancel, the same greeting — not
  a stripped-down version. Drop-in via one `<script src="widget.js">` include on any page that also
  loads `style.css`.

**Dashboard:** login, ticket list/filters, detail/status/reassign, review queue are built (T23–T24).

**Still open, worth knowing about:**
- **T09** (15 test sentences + 3 voice samples) is **partially done**: 3 real voice samples now
  exist at `submission/t09-voice-samples/` (recovered from real citizen-simulation recordings
  already sitting in the Supabase `audio` bucket, not freshly recorded — see that folder's
  `README.md` for provenance). The **15 text test sentences are still not written**.
- **T13** (prompt tests, ≥13/15) is blocked on T09's 15 sentences specifically.
- **T28** (explicit end-to-end cancel/restart/timeout verification), **T30** (dashboard map),
  **T31** (full 10-scenario integration pass), **T32** (deploy) are the remaining backend/product
  work.
- **T52**'s two human-only checklist items (above).
- Phase 3 (submission documents, T33–T43) and Phase 4 (event prep) haven't started, and the
  submission deadline is very close — check today's date against it before starting new
  engineering work versus submission-prep work.

## Run it locally

```powershell
# backend (real API)
cd backend; uv sync; uv run uvicorn app.main:app --port 8000     # http://localhost:8000/docs
# backend (mock — canned responses, no real API keys needed)
cd backend; uv run uvicorn mock.app:app --port 8001
# tests
cd backend; uv run pytest
cd backend; uv run ruff check .
# dashboard
cd dashboard; uv sync; uv run streamlit run src/dashboard/app.py
# website (serves index.html, status.html, widget.js, all of frontend/)
cd frontend; python -m http.server 5500
```

Copy `.env.example` to `.env` and fill in real values — **never commit `.env`**. Every var's comment
in `.env.example` explains what it's for and, where relevant, when it was last live-checked.
`frontend/app.js`, `status.js`, and `widget.js` all hardcode `API_BASE = 'http://localhost:8000'` —
if you're testing from a phone/another device on the same network rather than the same machine
running the backend, that constant needs to be your machine's LAN IP instead, plus that origin
added to `ALLOWED_ORIGINS`.

## Repo layout

| Path | Usually | Purpose |
|---|---|---|
| `backend/app/` | Dev | FastAPI core — see below |
| `backend/mock/` | Dev | Canned-response mock API, what the frontend was originally built against |
| `backend/tests/` | Dev | pytest, incl. `tests/contract/` (shared mock+real contract suite) |
| `dashboard/` | Lead | Streamlit officer dashboard |
| `frontend/` | Lead (redesign work has been Dev too) | Citizen website (HTML/CSS/vanilla JS): `index.html`/`app.js` (full chat), `status.html`/`status.js` (status lookup), `widget.js` (floating widget, full parity with `app.js`), `style.css` (shared by all three) |
| `database/` | Lead | `schema.sql`, `seed.sql` |
| `specs/` | Lead | Service definitions (YAML), e.g. `water_supply.yaml` |
| `docs/specs/` | Both | **The real documentation** — one file per module, written before the code, `S01`–`S19` |
| `docs/plans/` | Both | File-by-file build plans, one per ticket, written after the spec and before the code, each ending in a build log of what was actually verified live |
| `docs/problems/` | Both | Real bugs found post-ship, written up the same way a spec is (root cause, repro, fix) — e.g. `T50-app-js-network-fallback.md` |
| `docs/T52-designer-brief.md` | Lead | The actual product brief for the T52 redesign — read before `docs/specs/S18-*` if you're touching the citizen UI |
| `docs/` | Both | `PROJECT.md`, `TICKETS.md`, `GAPS.md`, this file |
| `submission/` | Lead | Hackathon submission documents, incl. `t09-voice-samples/` |

## How this project was built (so the pattern doesn't surprise you)

Every ticket in `docs/TICKETS.md` — backend and frontend alike — followed the same sequence:

1. **Spec** (`docs/specs/S*.md`) — what the module does, its exact behavior, the decisions made and
   why, and what's deliberately left open (`OPEN`/`G-*` items). `S01`–`S14` are backend; `S15`–`S19`
   are frontend (status page, mic/location, TTS, the T52 redesign, the T53 widget).
2. **Plan** (`docs/plans/T*-plan.md`) — turns the spec into a concrete file list and near-final
   code, reviewed before anything is written, then a **build log appended after implementation**
   recording exactly what was verified live and what wasn't (be honest here — several plans
   explicitly flag things like "this session has no physical microphone, a human still needs to
   verify X").
3. **Implementation** — unit tests against fakes/mocks where they exist, then a live check against
   the real external service/real backend before calling it done.

The result: `backend/app/turn_engine.py` (S05), `session.py` (S06), `validator.py` (S07),
`jurisdiction.py` (S09), `ticketing.py` (S10/S11), `voice.py` (S12, ASR), `tts.py` (S17, TTS),
`routes.py` (S04, orchestrates all of the above). Frontend: `frontend/status.js` (S15),
`app.js`'s mic/location/S18 redesign (S16/S18), `app.js`'s speak buttons (S17), `widget.js` (S19).
Each has its own spec and was live-verified against the real provider/backend before being marked
done — not just unit tested against a fake.

## Things worth knowing before you touch the code

- **External model names drift.** More than once, a hardcoded model id (Groq's `llama-3.3-70b-
  versatile`, Gemini's flagship variants) stopped working mid-project — not an outage, the model
  was retired or renamed. `.env.example`'s `*_MODEL` comments say when they were last live-checked;
  if something that used to work suddenly 404s or "model not found"s, check that first.
- **No FFmpeg**, deliberately (`docs/specs/S12-voice.md` D-S12-1). Both Sarvam and Groq Whisper
  accept the browser's native `webm`/`ogg`/`mp4`/`wav` directly.
- **No build step, no module system, anywhere in `frontend/`.** This is deliberate
  (`docs/PROJECT.md` §9: both team members must be able to explain every line to judges). One
  consequence: `app.js` and `widget.js` **duplicate** a fair amount of logic (request building,
  error handling, the recording state machine) rather than sharing a module — documented as a
  real, considered tradeoff (S19 D-S19-2), not an oversight. If you change one, check whether the
  other needs the same change.
- **A citizen must never see a raw browser/JS error.** This exact bug (`fetch()`'s own English
  error, or an uncaught exception, leaking into a chat bubble instead of the Hindi fallback) has
  been found and fixed **three separate times** in three different files — `status.js`, `app.js`,
  and a `setPointerCapture` edge case in the mic gesture. See `docs/problems/T50-app-js-network-
  fallback.md`. Every `fetch()` and every browser API call (`getUserMedia`, `setPointerCapture`,
  `audio.play()`) needs its own `try`/`catch` collapsing to a citizen-safe Hindi message — never
  assume a browser API can't throw.
- **Browser autoplay policy blocks unprompted audio.** T52's auto-playing greeting will reliably
  fail to autoplay on a genuinely fresh page load (no prior user gesture) — this is intentional
  browser security behavior, not a bug, and there's no way to force it. Always build a visible
  fallback (a tap-to-listen button) for any autoplay attempt; never assume it will just work.
- **A known, documented concurrency gap**: two genuinely simultaneous requests with the same
  `message_id` could both pass the dedupe check before either commits
  (`docs/specs/S06-session-manager.md` G-S06-1). Not fixed — flagged for T31, low priority at
  hackathon-demo traffic levels.
- **DB calls have explicit, short timeouts** (`backend/app/db.py`, 10s/15s) — `supabase-py`'s own
  defaults are 120s/20s, which would hang a citizen's request for two minutes on any DB hiccup.
- **Every external call has a fallback and a citizen-safe failure mode.** Groq→Gemini (LLM),
  Sarvam→Groq Whisper (ASR), both providers down → clean `503`, never a hang or a stack trace to
  the citizen. If you add a new external call, match this pattern.

## Team workflow

`git pull` before starting; push when something works. Unclear rule or spec? Ask the other person,
and update the spec if the answer matters — specs are meant to be the durable record of *why*, not
just what. If you find a real bug in already-shipped work, write it up in `docs/problems/` the same
way a spec is written (root cause, repro, suggested fix) before fixing it or handing it off.
