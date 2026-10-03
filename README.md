# Samadhan (समाधान)

**A voice-first citizen grievance assistant for Madhya Pradesh.** A citizen speaks or types a complaint in Hindi, Hinglish or a
local dialect. Samadhan works out what kind of message it is, picks the right **department**, asks only for what is missing, and after
the citizen confirms, files a ticket (`SMD-xxxx`) at the right **office**. The citizen can check status by complaint number, typed or
spoken. Officers manage tickets, corrections and a map on a dashboard.

> **The idea:** understand a complaint well enough to *route* it. We do not need to transcribe a dialect perfectly.

Built for the **MPOnline Idea & Innovation Hackathon 2026, Problem Statement 5**. Target: all of **Madhya Pradesh** (the demo data currently covers a few Bhopal offices; more districts are added as data, not code).

> **Read this honestly.** Water supply (Jal Vibhag) was the original pilot service. Electricity, roads, sanitation and a general-triage
> desk were added for the demo, and **all of their office data is DEMO** (constructed, labelled `(DEMO)` in the office name; nothing is
> sourced from a government list). Ward names are unverified. The dialect test data is **synthetic**. See [Known limitations](#known-limitations).

---

## What it does

- **Speak, type, or share location.** Tap-to-record voice with a live waveform and a 1-minute limit (Sarvam speech-to-text, Groq Whisper as fallback; optional Gemini audio reader, see `docs/specs/S32-asr-router.md`), text, and a GPS button.
- **Understands the kind of message first.** Every message is a *complaint*, an *information question*, a *status question*, or
  *out of context*. Each gets the right reply.
- **Multi-department routing.** A complaint goes to water, electricity, roads, sanitation, or a *general triage* desk when it fits none.
  If it is unsure it asks "is this X or Y?", or reconfirms ("are you reporting X?"). The questions are written by us, not generated.
- **Asks only what is missing** (issue, then location), summarises, and files after the citizen confirms. Corrections work without a restart.
- **Routes to an office.** A ward name is matched to the ward office; anything unknown goes to the department's district office marked
  `needs_review`. An officer can move a wrongly routed ticket to another department.
- **Information questions** ("how do I get an income certificate?") get an honest fixed reply, a link to a real `.gov.in` site
  (proposed by the LLM, then strictly validated by the backend) and a disclaimer. Nothing about documents is invented.
- **Check status in the chat**: type or say the complaint number (`SMD-0022`, `S M D 0 0 2 2`, `एसएमडी शून्य शून्य दो दो`). Also a
  separate status page.
- **Voice replies.** Every bot reply is a playable voice note (Sarvam text-to-speech); replies to a voice message play automatically.
- **Cancel / restart / 30-minute timeout**, typed or spoken, and a new complaint after a cancel starts clean.
- **Resilient by design.** LLM chain (three Groq models, then Gemini), ASR fallback, short timeouts, citizen-safe Hindi error messages.
- **Officer dashboard** (Streamlit): per-department open counts, filters, ticket detail with audio, status changes, cross-department
  reassign with an audit trail, a review queue, and a map of tickets with GPS.

## How it works

```
Citizen (browser: text / voice / GPS)
   |  POST /api/v1/message                                   GET /api/v1/status/{id}
   v
FastAPI core ----> [voice] Sarvam ASR -> Groq Whisper fallback  (audio + transcript kept)
   |
   |  command?  ("cancel", "रद्द करो") -> handled here, no LLM
   |  complaint number in the message?  -> status answered here, no LLM
   v
Turn Engine (ONE LLM call, strict JSON): intent, department, confidence, fields
   |   Groq gpt-oss-120b -> qwen3.8-27b -> gpt-oss-20b -> Gemini
   v
Validator (pure code): checks every value against the service spec, decides
   route / reconfirm / clarify / general triage / information reply / decline
   v
Jurisdiction (fuzzy ward match) -> Ticket SMD-xxxx -> Supabase (Postgres + private audio bucket)
                                                            ^
Officer dashboard (Streamlit) reads and writes the DB directly, never calls the API
```

Key rules: the LLM never invents a service, field, department or office (a service spec file is the only source); routing happens in the
core, not the website; the dashboard only shows stored data; secrets never reach the browser.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, uv, FastAPI, Uvicorn, Pydantic, httpx, PyYAML, RapidFuzz |
| LLM | Groq (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `openai/gpt-oss-20b`), Google Gemini as last fallback; called over HTTP, no SDK |
| Voice | Sarvam `saaras:v4` (speech-to-text) and `bulbul:v3` (text-to-speech); Groq `whisper-large-v3-turbo` as ASR fallback; no FFmpeg. Optional, off by default: Google Gemini (audio understanding as the main reader, `ASR_PIPELINE=router`; Gemini speech as a spoken-reply fallback, `TTS_PROVIDERS=sarvam,gemini`), S32 |
| Follow-up questions | Optional, off by default (`TRIAGE=1`): per-department question bank written with Google Gemini, read with the same LLM chain, S33 |
| Intake decisions (experimental, off by default) | TypeSafe AI Jev (`jev-latest`) over HTTP: department choice and yes/no judgements only; see `docs/specs/S30-intake-v2.md` |
| Data | Supabase (Postgres, Row Level Security, private Storage bucket `audio`) |
| Website | HTML, CSS and vanilla JavaScript (no build step); MediaRecorder and Geolocation browser APIs |
| Dashboard | Streamlit, pandas, folium and streamlit-folium (OpenStreetMap tiles) |
| Tooling | pytest, Ruff, uv, Docker |
| Hosting (planned) | Railway or Render (API), Vercel or Render (website), Streamlit Community Cloud or Render (dashboard) |

## Quick start (local, from a fresh clone)

**You need:** Git, Python 3.12+, [uv](https://docs.astral.sh/uv/), and a Supabase project plus API keys for the real backend.
No keys? Use the mock backend (below) to try the website.

```bash
git clone https://github.com/krishnakantnagina/Samadhan.git
cd Samadhan
cp .env.example .env        # Windows: copy .env.example .env   then fill in the values (never commit .env)
```

**1. Database (once).** In your Supabase project run, in this order, `database/schema.sql`, `database/seed.sql`,
`database/seed_departments.sql` (and optionally `database/seed_tickets.sql` for sample tickets). Create a **private** Storage bucket
named `audio`. Details: `docs/specs/S02-db-schema.md`.

**2. Run the three parts** (three terminals):

```bash
# backend API   http://localhost:8000/docs
cd backend && uv sync && uv run --env-file ../.env uvicorn app.main:app --port 8000

# website       http://localhost:5500   (also works on http://127.0.0.1:5500)
cd frontend && python -m http.server 5500

# officer dashboard   http://localhost:8501
cd dashboard && uv sync && uv run --env-file ../.env streamlit run src/dashboard/app.py --server.port 8501
```

The website calls the API on the same host name you opened it with. `ALLOWED_ORIGINS` in `.env` must include the website's origin
(the example file already lists `localhost` and `127.0.0.1` on ports 3000 and 5500). Log in to the dashboard with `DASHBOARD_PASSWORD`.

**Mock mode (no keys, no database):** `cd backend && uv run uvicorn mock.app:app --port 8000` serves canned, schema-valid answers so the
website can be developed without any provider.

### Try it
Type or say: `बिजली नहीं आ रही` (electricity), `सड़क में गड्ढा है` (roads), `कचरा नहीं उठा` (sanitation), `पानी नहीं आ रहा` (water),
`आय प्रमाण पत्र कैसे बनवाएं?` (information), a joke (out of context), `SMD-0022` (status), `रद्द करो` (cancel).

## Configuration

Copy `.env.example`; every variable is commented there. Main ones:

| Variable | Used by | Notes |
|---|---|---|
| `GROQ_API_KEY`, `GEMINI_API_KEY` | API | LLM providers; `GROQ_MODEL`, `GEMINI_MODEL`, `GROQ_FALLBACK_MODELS`, `GROQ_REASONING_EFFORT`, `LLM_PROVIDER` tune them |
| `AUTH_PROVIDER`, `AUTH_REQUIRED` | API | phone registration (S31): `demo` = any phone + fixed PIN 5555, for the hackathon demo only and refused on a production host; `AUTH_REQUIRED=1` makes a login necessary to file a complaint; `AUTH_IDLE_DAYS`, `AUTH_MAX_DAYS` tune the saved login; apply `database/migrations/002` first |
| `INTAKE_V2`, `TYPESAFE_API_KEY` | API | experimental guided intake (Jev decides the department); off unless both are set, never enable on real citizen data before the data terms are read; `TYPESAFE_MODEL` tunes it |
| `SARVAM_API_KEY` | API | speech-to-text and text-to-speech; `SARVAM_MODEL`, `SARVAM_TTS_MODEL`, `SARVAM_TTS_SPEAKER`, `GROQ_WHISPER_MODEL` |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | API, dashboard | server-side only; the website never holds a database key |
| `ALLOWED_ORIGINS` | API | comma-separated website origins allowed by CORS |
| `DASHBOARD_PASSWORD` | dashboard | shared officer password |
| `SAMADHAN_API_BASE` | website (build time) | only for a deployed website; see the deploy guides |

Model names drift: providers retire and rename models. `.env.example` records when each was last checked live.

## Tests

```bash
cd backend   && uv run pytest && uv run ruff check .     # 415 tests, no network, no keys needed
cd dashboard && uv run pytest                             # 35 tests
```
Live accuracy runs (they call the real providers, so they are **not** part of `pytest`):
`backend/tests/prompt/run_t13.py` (water-only extraction, 15 sentences) and `backend/tests/prompt/run_routing_eval.py`
(department routing). Run from `backend/` with `PYTHONPATH=. uv run --env-file ../.env python tests/prompt/<script>.py`.

## Deployment

See [`docs/DEPLOY.md`](docs/DEPLOY.md) (Railway API, Vercel website, Streamlit dashboard) or
[`docs/DEPLOY_RENDER.md`](docs/DEPLOY_RENDER.md) (everything on Render), and spec [`docs/specs/S22-deploy.md`](docs/specs/S22-deploy.md).
The API ships as a `Dockerfile` at the repo root (build context = the repo root, because it needs `specs/`). Phone browsers only allow the
microphone and location on **HTTPS**, which the hosts provide.

## Repository layout

| Path | What |
|---|---|
| `backend/app/` | FastAPI core: routes, turn engine, validator, jurisdiction, ticketing, session, voice, tts, status and info replies |
| `backend/mock/` | canned-response mock API for website development and the shared contract tests |
| `backend/tests/` | pytest, plus `tests/prompt/` live evaluation scripts |
| `frontend/` | citizen website: `index.html` (hero; the chat is `widget.js`, S31; `app.js` is kept but unused), `status.html` + `status.js`, `widget.js` (floating chat), `style.css` |
| `dashboard/` | Streamlit officer dashboard |
| `specs/` | service definitions in YAML: `water_supply`, `electricity`, `roads`, `sanitation`, `general` |
| `database/` | `schema.sql`, `seed.sql`, `seed_departments.sql`, `seed_tickets.sql` |
| `docs/` | `PROJECT.md` (source of truth), `TICKETS.md`, `specs/S01-S29` (one spec per module, written before the code), `plans/`, `research/` |
| `submission/` | hackathon submission material and evaluation results |

## Documentation

- [`docs/PROJECT.md`](docs/PROJECT.md): scope, request flow, rules, definition of done. Start here.
- [`docs/ONBOARDING.md`](docs/ONBOARDING.md): a new developer's orientation.
- [`docs/TICKETS.md`](docs/TICKETS.md): the checklist and honest status notes.
- [`docs/specs/`](docs/specs/): API contract (S01), DB schema (S02), service spec format (S03), turn engine (S05), routing (S28), status in chat (S29), and more.
- [`docs/ARCHITECTURE_DEPARTMENTS.md`](docs/ARCHITECTURE_DEPARTMENTS.md): what the research says about department structure, and a proposal for managing it centrally.

## Results so far (honest numbers)

- **Routing:** about **90%** exact on 60 messages (26 hand-written + 34 from synthetic Bundeli and Malvi data): hand-written 25/26, synthetic 29-30/34.
  The remaining misses are mostly debatable labels. One run each; synthetic data written by an LLM, not checked by native speakers.
- **Water-only extraction (T13):** 12-13 of 15 on the two best runs (six runs in total: 11, 10, 9, 9, 13, 12), so the 13/15 target was met once.
- **End to end (scripted, real providers):** all ten definition-of-done scenarios exercised; scenario 7 (GPS to the correct ward) cannot pass yet, see below.
- **Tests:** 415 backend and 35 dashboard tests pass; Ruff clean.

## Known limitations

- **Demo data.** Office rows for electricity, roads, sanitation and general triage are constructed and marked `(DEMO)`. The five pilot ward names
  are unverified; zone-to-ward mapping, ward centres and officer names were **not found** (`docs/research/T05-research.md`).
- **GPS does not choose a ward yet.** Ward centre points are empty, so a GPS-only complaint goes to the district office as `needs_review`. GPS is
  used for the officer map. Routing by ward works from the place name.
- **Free-tier capacity.** Groq's free tier allows about 8,000 tokens per minute per model, so a burst of users can exhaust it; the fallback chain
  absorbs most of it. Free hosts also sleep when idle.
- **No per-department officer accounts** (one shared dashboard password), and **no push notification** to an officer when a ticket arrives.
- **No rate limit or login** on the citizen endpoints (`/message`, `/speak`).
- **Spoken complaint numbers** are understood as digits and digit words, not as Hindi number words ("बाईस").
- **Information questions** get a link and a disclaimer, not an answer: there is no verified knowledge base.
- The submitted state is tagged `v1-mvp`.

## Attribution

Every library, API, data source and template used (hackathon organizer requirement). Keep this list up to date.

**Backend** (`backend/pyproject.toml`)
- [FastAPI](https://fastapi.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/), [Uvicorn](https://www.uvicorn.org/) (with its `standard` extras), [python-multipart](https://github.com/Kludex/python-multipart)
- [httpx](https://www.python-httpx.org/), [PyYAML](https://pyyaml.org/) (service spec loader)
- [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) (fuzzy ward-name matching)
- [supabase-py](https://github.com/supabase/supabase-py) (Supabase client)
- Dev: [pytest](https://pytest.org/), [Ruff](https://docs.astral.sh/ruff/)

**Dashboard** (`dashboard/pyproject.toml`)
- [Streamlit](https://streamlit.io/), [pandas](https://pandas.pydata.org/), [python-dotenv](https://github.com/theskumar/python-dotenv), [supabase-py](https://github.com/supabase/supabase-py)
- [folium](https://python-visualization.github.io/folium/) and [streamlit-folium](https://github.com/randyzwitch/streamlit-folium) (maps; folium bundles [Leaflet](https://leafletjs.com/))
- Map tiles: [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL)
- Dev: pytest

**Website**: no framework, no build step, no third-party JavaScript, fonts or CSS. Browser APIs only: MediaRecorder, Geolocation, Audio.

**AI and cloud services**
- [Groq API](https://console.groq.com/docs): LLM (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `openai/gpt-oss-20b`) and Whisper speech-to-text fallback (`whisper-large-v3-turbo`)
- [Google Gemini API](https://ai.google.dev/gemini-api/docs): last-resort LLM fallback
- [Sarvam AI](https://docs.sarvam.ai/): speech-to-text (`saaras:v4`) and text-to-speech Bulbul (`bulbul:v3`)
- [TypeSafe AI](https://docs.typesafe.ai/): Jev decision model for department routing (experimental, behind `INTAKE_V2`)
- [Supabase](https://supabase.com/): Postgres and Storage

**Hosting and build**: [Railway](https://railway.com/), [Vercel](https://vercel.com/), [Render](https://render.com/), [Streamlit Community Cloud](https://streamlit.io/cloud); container base image [`ghcr.io/astral-sh/uv`](https://github.com/astral-sh/uv); [uv](https://docs.astral.sh/uv/).

**Data**
- Pilot ward names come from the unofficial OpenCity.in / Esri India Living Atlas ward list (via [bharatlas.com](https://bharatlas.com/view/wards_bhopal)); **unverified**, marked DEMO.
- Bhopal Municipal Corporation head-office details: [bhopal.nic.in](https://bhopal.nic.in/en/public-utility/bhopal-municipal-corporation/) (official).
- Synthetic Bundeli and Malvi conversation files were used only for evaluation; they are not in this repository. All sample tickets in `database/seed_tickets.sql` are synthetic.

**Development process**: built with the assistance of Claude Code (Anthropic), spec-first: every module has a written spec (`docs/specs/`) and a plan (`docs/plans/`).


