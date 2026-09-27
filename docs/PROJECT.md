# Samadhan — PROJECT.md

Context for Claude Code. Read this first, then the ticket, then only the specs it needs.
Unknown items are `TBD`: never guess; ask the team or note it in `docs/GAPS.md`.

## 1. What We Are Building
A voice-first **AI chatbot website** for citizen grievances in Madhya Pradesh.
Citizen speaks or types (Hindi / Hinglish) → AI asks only for missing details → citizen confirms →
ticket `SMD-xxxx` is created and routed to the correct **department + ward office** →
citizen checks status by complaint ID. Officers manage tickets on a dashboard.

MPOnline Idea & Innovation Hackathon 2026, Problem Statement 5. Submit by **noon, 30 Sep 2026**
and tag `v1-mvp`. No changes to the submitted code until the event ends (10 Oct).

## 2. Scope
| Build now | Not now |
|---|---|
| Website chatbot: text, in-browser voice, GPS, status page | WhatsApp, calls, mobile app |
| 1 service: `water_supply` (Jal Vibhag) | Other services |
| Pilot: Bhopal, 5 wards + 1 district fallback office | Statewide data |
| Anonymous citizen sessions | OTP / phone verification |
| Dashboard: password login, list, detail, status, reassign, review queue, map | Officer accounts, per-department access |
| ASR + LLM fallbacks; `cancel`, `restart`, 30-min timeout | TTS reply, rate limiting, analytics |

## 3. Repo Layout
```text
backend/            FastAPI core (Dev A)
  app/schemas.py    API models, implements docs/specs/S01
  mock/             Mock API for website development
  tests/            pytest
dashboard/src/      Streamlit officer dashboard (Lead)
frontend/           Citizen website: HTML, CSS, vanilla JS (Lead)
database/           schema.sql, seed.sql, implements docs/specs/S02
specs/              Service specs (YAML), e.g. water_supply.yaml
docs/specs/         Feature specs S01–S16
docs/               PROJECT.md, TICKETS.md, GAPS.md
submission/         Hackathon submission documents
```

## 4. Request Flow and Rules
```text
1. Website → POST /api/v1/message (text or audio, optional lat/lng, session_id, message_id)
2. Duplicate message_id → return stored response
3. Audio → FFmpeg (16 kHz mono WAV) → Sarvam ASR → transcript (keep original audio + transcript)
4. Load session → Turn Engine (ONE LLM call, strict JSON)
5. Backend validates against the service spec → ask next question OR ask citizen to confirm
6. Confirmed → jurisdiction resolver → office for department + ward
7. Create ticket SMD-xxxx. No ward match or confidence < 0.7 → district office + needs_review
8. Reply with complaint ID + office
9. Officer updates status / reassigns on dashboard (reassign logged in routing_corrections)
10. Website → GET /api/v1/status/{complaint_id} → status, department, updated_at only
```
- Routing happens in the **core**. The website talks only to the API. The dashboard reads/writes the DB directly, only displays stored data, and never calls the core.
- Prompt = session state + active service spec + last ~4 messages. Specs are loaded once at startup.
- LLM output is always validated with Pydantic. The LLM must never invent services, fields, departments, offices or rules.
- Timeouts: ASR ~8 s, LLM ~6 s, then fallback provider.
- Jurisdiction: GPS → nearest ward centroid; ward/village name → fuzzy match (`rapidfuzz`) on `offices.name` + `aliases`.

## 5. Contracts
| Contract | Spec | Code |
|---|---|---|
| API | `docs/specs/S01-api-contract.md` | `backend/app/schemas.py` |
| DB | `docs/specs/S02-db-schema.md` | `database/schema.sql`, `database/seed.sql` |
| Service | `docs/specs/S03-service-spec-format.md` | `specs/water_supply.yaml`, loaded by core |

Change a contract → update spec + code together and tell the teammate.

- Endpoints: `POST /api/v1/message`, `GET /api/v1/status/{complaint_id}`, `GET /health`
- `action`: `ask` · `confirm` · `submitted` · `cancelled` · `out_of_scope` · `error`
- Ticket status: `new` · `in_progress` · `resolved` · `needs_review`
- Complaint ID: `SMD-` + number, zero-padded to ≥ 4 digits, never truncated
- Tables: `sessions`, `messages`, `tickets`, `offices`, `routing_corrections`

## 6. Tech Stack
| Layer | Choice |
|---|---|
| Backend | Python 3.12, uv, FastAPI (async), Uvicorn, Pydantic, httpx, PyYAML, rapidfuzz |
| Voice | FFmpeg; Sarvam Saarika ASR → fallback Groq Whisper |
| LLM | Groq (JSON mode) → fallback Gemini Flash |
| Data | Supabase Postgres + private Storage bucket `audio` |
| Website | HTML, CSS, vanilla JS, MediaRecorder, Geolocation API; mobile-first, Hindi-first |
| Dashboard | Streamlit, folium + streamlit-folium, pandas |
| Tooling | pytest, Ruff, Git/GitHub |
| Hosting | Railway (API), Vercel (website), Streamlit Community Cloud (dashboard); demo also runs locally |

## 7. Commands
```powershell
# backend (mock API today; real API is app.main:app once it exists)
cd backend; uv sync; uv run uvicorn mock.app:app --reload     # http://localhost:8000/docs
cd backend; uv run pytest
cd backend; uv run ruff check .
# dashboard (entry file TBD in dashboard/src/)
cd dashboard; uv sync; uv run streamlit run src/<entry>.py
# website
cd frontend; python -m http.server 5500
```

## 8. Security
- Secrets only in `.env` (and Streamlit secrets); never commit keys. `.env.example` lists names only.
- Env vars: `SARVAM_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DASHBOARD_PASSWORD`, `ALLOWED_ORIGINS`.
- Service key server-side only (core, dashboard). Anon key has **no** access (RLS on, no public policies). The website holds no DB keys.
- CORS allows only origins in `ALLOWED_ORIGINS`.
- Status endpoint returns only complaint ID, status, department, updated time.
- Keep original audio + transcript unchanged. No citizen contact details stored.

## 9. Coding Rules for Claude Code
1. Implement only the current ticket; follow its spec's ACCEPTANCE list.
2. Never invent business rules. If a spec is unclear, stop and ask.
3. Don't edit files outside the ticket's area without saying so first.
4. Every new library or API → add to the Attribution section of `README.md` (hackathon rule).
5. Write or update tests for backend logic; run `uv run pytest` before saying done.
6. Keep code explainable: both team members must be able to explain every line to judges.

## 10. Definition of Done
All 10 scenarios pass:
1. Hindi voice "3 दिन से पानी नहीं आ रहा" → asks only for location
2. Hinglish text → same flow
3. All details in one message → straight to confirmation
4. Correct a field at confirmation → updates without restart
5. `cancel` → session cleared
6. Unrelated request → polite out-of-scope, no invented service
7. GPS in pilot ward → correct ward office
8. Unknown location → district office + `needs_review`
9. Officer sets "In progress" → status check shows it
10. Two browsers at once → sessions never mix

## 11. Open (TBD)
Citizen verification method · officer per-department access · dialects beyond Hindi/Hinglish ·
dashboard entry file name · custom domain · data retention.
