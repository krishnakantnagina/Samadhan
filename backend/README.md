# Backend

FastAPI core. Contract: [`docs/specs/S01-api-contract.md`](../docs/specs/S01-api-contract.md) and
[`app/schemas.py`](app/schemas.py). Uses `uv`; run everything from this folder.

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
