# Backend

FastAPI core. Contract: [`docs/specs/S01-api-contract.md`](../docs/specs/S01-api-contract.md) and
[`app/schemas.py`](app/schemas.py). Uses `uv`; run everything from this folder.

## Real API (T07)

App setup only today — config, CORS, `/health`, startup loading of `specs/*.yaml`. No
`/message`/`/status` logic yet (T18/T19). Spec: `docs/specs/S04-message-endpoint.md`.

```bash
uv run uvicorn app.main:app --port 8000
```

## Mock API (T08)

Schema-valid canned responses for every `action`, so the website can be built before the real backend exists.

```bash
uv run uvicorn mock.app:app --port 8000
```

Mock-only triggers: send text `mock:<trigger>` with `ask`, `confirm`, `submitted`, `submitted_district`,
`cancelled`, `out_of_scope` or `error`. Seeded tickets: `SMD-0042` (`in_progress`), `SMD-0007` (`needs_review`).

## Contract tests

The same suite runs against the mock or the real API.

```bash
uv run pytest                                          # mock, in-process
BASE_URL=http://localhost:8000 uv run pytest           # a running mock, over HTTP
BASE_URL=<url> CONTRACT_TARGET=real uv run pytest      # the real backend (skips mock_only tests)
```

| Env var | Purpose |
|---|---|
| `ALLOWED_ORIGINS` | Comma-separated website origins allowed by CORS (S01 §9, rule 4) |
| `CONTRACT_EXISTING_ID` | A ticket that exists on the target (default `SMD-0042`) |
| `CONTRACT_ALLOWED_ORIGIN` | An origin listed in the target's `ALLOWED_ORIGINS` (default `http://localhost:3000`) |

## Lint

```bash
uv run ruff check . && uv run ruff format --check .
```

## Local test mode (private database, never the live Supabase)

Test the real backend, every department and the whole route without touching the live server. It runs a private Postgres on port 5544
(data in `local-research/devdb/`, git-excluded) and replaces the Supabase client with a small adapter. `SUPABASE_*` are overwritten with dummy
values before the app starts, so the live database cannot be reached from this process.

```bash
python scripts/local_dev_db.py setup          # once: create + start the private DB, load schema, seeds and migrations 002..004
uv run --env-file ../.env --with "psycopg[binary]" python scripts/local_dev_server.py      # API on http://127.0.0.1:8000
(cd ../frontend && python -m http.server 5500)                                              # website on http://localhost:5500
uv run python scripts/try_complaint.py "mere gaon ke school me mid day meal nahi mil raha"  # talk to it from the terminal
uv run python scripts/try_complaint.py --scenarios                                           # one complaint per department
python scripts/local_dev_db.py tickets        # see what was filed;  stop | status | reset
```

All 49 registry departments have a spec (`scripts/gen_department_specs.py` generates them, the routes in `specs/registry/routes.yaml`
and the offices in `database/migrations/004_all_department_offices.sql`). Migration 004 is **not** applied to the live database yet.
The LLM providers are still called for real (Groq/Gemini free tiers answer 429 if turns come too fast; the test script pauses between turns).
The dashboard still reads the live database, so use `local_dev_db.py tickets` to see local tickets.
Voice: if Sarvam is out of credit (`/speak` answers 503, log shows `402`), start the server with `TTS_PROVIDERS=gemini,sarvam` (Gemini speech, may still
answer 429 or return a glitched clip); the website widget then falls back to the browser's own Hindi voice when the server voice fails.
No TTS credit? Open the website with `?voice=browser` (http://localhost:5500/?voice=browser) and replies are read in Hindi by the browser's own voice; the widget then never calls `/speak`.
Needs a Hindi voice installed in the browser/OS (Windows: Settings > Time & language > Speech).

Understand first (S35): start the local server with `UNDERSTAND_FIRST=1 uv run --env-file ../.env --with "psycopg[binary]" python scripts/local_dev_server.py` and Gemini translates the first
message and decides complaint / question / document request / greeting / unclear before routing (docs/specs/S35-understand-first.md).
