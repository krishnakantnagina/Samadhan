# Dashboard

Officer dashboard. Streamlit, reads/writes Supabase directly — never calls the core API
(PROJECT.md section 5). Contract: [`docs/specs/S13-dashboard-auth-list.md`](../docs/specs/S13-dashboard-auth-list.md).

## Run

```bash
uv sync
uv run streamlit run src/dashboard/app.py
```

Requires `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DASHBOARD_PASSWORD` in `.env` at the repo root —
the same file the backend uses. `app.py` loads it via `python-dotenv`.

## Tests

```bash
uv run pytest
```

## Today (T23)

Password gate + a filterable, read-only ticket list. Status change, reassignment, review-queue
actions, and the map are later tickets (T24, T30) — not built yet.
