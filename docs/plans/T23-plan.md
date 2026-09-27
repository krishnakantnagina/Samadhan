# Plan: T23 — Dashboard: login, list, filters

Ticket: `docs/TICKETS.md` T23 (owner Lead, depends on T20 — `[x]`, done when "Tickets listed").
Spec: `docs/specs/S13-dashboard-auth-list.md` (new).

**Scope: T23 only.** Read-only: password gate + a filterable ticket list. No status changes, no
reassignment, no review-queue actions, no map — those are T24/T30, each gets its own spec when
picked up. This plan does not write any of that.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `dashboard/src/dashboard/config.py` | Create | `get_dashboard_config()` — `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DASHBOARD_PASSWORD` (all required, fail fast) |
| `dashboard/src/dashboard/db.py` | Create | `get_client()` — same shape as `backend/app/db.py`, its own module (separate `uv` project) |
| `dashboard/src/dashboard/tickets.py` | Create | `list_tickets()` — the one read query T23 needs |
| `dashboard/src/dashboard/app.py` | Create | Streamlit entry point: auth gate, filters, table (D-S13-1) |
| `dashboard/tests/test_config.py` | Create | Missing-env-var tests, mirrors `backend/tests/test_config.py` |
| `dashboard/tests/test_tickets.py` | Create | `list_tickets()` against a fake client (query shape, not a live DB) |
| `dashboard/pyproject.toml` | Edit | Add `pytest` to the dev dependency group (not present yet) |
| `.env.example` | Edit | Add `DASHBOARD_PASSWORD=` (named in PROJECT.md §8, never actually added) |
| `dashboard/README.md` | Edit | Currently empty — add the real run command |
| `docs/PROJECT.md` §7, §11 | Edit | Fill in the entry file name; drop the resolved TBD item |
| `docs/TICKETS.md` | Edit (last step) | Tick T23 `[x]` |

`dashboard/src/dashboard/__init__.py` (the existing `main()` stub) is untouched — the real entry
point is `app.py`, run directly by `streamlit run`, not through the console-script `main()`.

## 2. Steps, in order

**S1 — `dashboard/src/dashboard/config.py`.**
```python
import os
from dataclasses import dataclass


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


@dataclass(frozen=True)
class DashboardConfig:
    supabase_url: str
    supabase_service_key: str
    dashboard_password: str


def get_dashboard_config() -> DashboardConfig:
    return DashboardConfig(
        supabase_url=_require("SUPABASE_URL"),
        supabase_service_key=_require("SUPABASE_SERVICE_KEY"),
        dashboard_password=_require("DASHBOARD_PASSWORD"),
    )
```
Same `_require` pattern as `backend/app/config.py` — duplicated on purpose (S13 DATA ACCESS: two
separate `uv` projects, no shared package).

**S2 — `dashboard/src/dashboard/db.py`.**
```python
from functools import lru_cache
from supabase import Client, create_client
from dashboard.config import get_dashboard_config


@lru_cache
def get_client() -> Client:
    config = get_dashboard_config()
    return create_client(config.supabase_url, config.supabase_service_key)
```

**S3 — `dashboard/src/dashboard/tickets.py`.**
```python
from typing import Any
from supabase import Client
from dashboard.db import get_client

TICKET_COLUMNS = "complaint_id,status,department,summary_en,created_at,updated_at,offices(office_name,level)"


def list_tickets(*, client: Client | None = None) -> list[dict[str, Any]]:
    client = client or get_client()
    return (
        client.table("tickets")
        .select(TICKET_COLUMNS)
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    ).data
```
(S13 BEHAVIOR §1 — never `select("*")`, matches S11's `get_status` posture.)

**S4 — `dashboard/src/dashboard/app.py`.**
```python
import secrets

import pandas as pd
import streamlit as st

from dashboard.config import get_dashboard_config
from dashboard.tickets import list_tickets

st.set_page_config(page_title="Samadhan — Officer Dashboard", layout="wide")


@st.cache_data(ttl=30)
def _cached_tickets() -> pd.DataFrame:
    rows = list_tickets()
    df = pd.json_normalize(rows)
    df = df.rename(columns={"offices.office_name": "office_name", "offices.level": "office_level"})
    return df


def _require_login() -> None:
    if st.session_state.get("authenticated"):
        return
    st.title("Samadhan — Officer Dashboard")
    password = st.text_input("Password", type="password")
    if st.button("Log in"):
        config = get_dashboard_config()  # raises at startup if unset, same posture as backend
        if secrets.compare_digest(password, config.dashboard_password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()


def main() -> None:
    _require_login()

    with st.sidebar:
        st.button("Log out", on_click=lambda: st.session_state.pop("authenticated", None))

    df = _cached_tickets()
    if df.empty:
        st.info("No tickets yet.")
        return

    st.title("Tickets")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        statuses = st.multiselect("Status", sorted(df["status"].unique()), default=list(df["status"].unique()))
    with col2:
        departments = ["All"] + sorted(df["department"].unique())
        department = st.selectbox("Department", departments)
    with col3:
        office_pool = df if department == "All" else df[df["department"] == department]
        offices = ["All"] + sorted(office_pool["office_name"].dropna().unique())
        office = st.selectbox("Office", offices)
    with col4:
        search = st.text_input("Search complaint ID")

    filtered = df[df["status"].isin(statuses)]
    if department != "All":
        filtered = filtered[filtered["department"] == department]
    if office != "All":
        filtered = filtered[filtered["office_name"] == office]
    if search:
        filtered = filtered[filtered["complaint_id"].str.contains(search, case=False, na=False)]

    st.dataframe(
        filtered[["complaint_id", "status", "department", "office_name", "summary_en", "created_at", "updated_at"]],
        use_container_width=True,
        hide_index=True,
    )


if __name__ == "__main__":
    main()
```
`needs_review` visual treatment (S13 BEHAVIOR §4): `st.dataframe` doesn't support per-cell styling
as cleanly as `st.table`/`pandas.Styler` — if a colour badge turns out to need more than
`st.dataframe`'s column config gives us once this is actually running, switch to
`df.style.apply(...)` + `st.table` at that point rather than guessing the right approach blind here.

**S5 — `dashboard/pyproject.toml`.** Add:
```toml
[dependency-groups]
dev = ["pytest>=9.1.1"]
```

**S6 — `dashboard/tests/test_config.py`.**
- `test_missing_supabase_url_raises`, `test_missing_service_key_raises`,
  `test_missing_dashboard_password_raises` — each via `monkeypatch.delenv`, `pytest.raises(RuntimeError, match=...)`.
- `test_parses_when_all_set`.

**S7 — `dashboard/tests/test_tickets.py`.**
A minimal fake client (same pattern as `backend/tests/test_ticketing.py`'s `FakeClient`): asserts
`list_tickets()` requests exactly `TICKET_COLUMNS`, orders by `created_at desc`, and returns the
fake's canned rows unchanged.

**S8 — Run the suite.** `cd dashboard; uv sync; uv run pytest`.

**S9 — `.env.example`.** Add `DASHBOARD_PASSWORD=` under the `SUPABASE_*` lines, with a comment
that it's shared between Lead/Dev and never committed with a real value (G-S13-1).

**S10 — `dashboard/README.md`.** Currently empty:
```markdown
# Dashboard

Officer dashboard. Streamlit, reads/writes Supabase directly — never calls the core API
(PROJECT.md section 5). Contract: `docs/specs/S13-dashboard-auth-list.md`.

## Run

\`\`\`bash
uv sync
uv run streamlit run src/dashboard/app.py
\`\`\`

Requires `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DASHBOARD_PASSWORD` in `.env` (repo root — same
file the backend uses; Streamlit reads it via `python-dotenv`, already a dependency).

## Tests

\`\`\`bash
uv run pytest
\`\`\`
```
One thing this surfaces: `python-dotenv` is already a dependency but nothing calls `load_dotenv()`
yet — add `from dotenv import load_dotenv; load_dotenv()` at the top of `app.py` (and in
`conftest.py` for tests, or just rely on the repo-root `.env` being picked up the same way) so
`uv run streamlit run ...` from `dashboard/` actually sees the root `.env` — `os.environ` alone
won't unless the shell already exported it. Streamlit itself does not auto-load `.env` files.

**S11 — `docs/PROJECT.md`.**
§7: replace the dashboard command line with the real one:
```
cd dashboard; uv sync; uv run streamlit run src/dashboard/app.py
```
§11: drop "dashboard entry file name" from the Open (TBD) list (D-S13-1 resolves it).

**S12 — Tick it off.** `docs/TICKETS.md`: T23 `[x]`, once S8 is green and a manual smoke test (S13
ACCEPTANCE) passes against the real seeded data (T20's 16 tickets).

## 3. Acceptance coverage

| S13 acceptance item | Satisfied by (code) | Verified by (test/manual) |
|---|---|---|
| "Tickets listed" | S3, S4 | Manual: run against live Supabase, see the 16 T20 rows |
| Wrong password → no access | S4 `_require_login` | Manual |
| Missing `DASHBOARD_PASSWORD` → fails at startup, names the var | S1 | S6 |
| Filters reflect real data | S4 (derived from `df`, not hardcoded) | Manual |
| No citizen-only fields fetched | S3 `TICKET_COLUMNS` | S7 |

## 4. New libraries
`pytest` (dev-only, dashboard project). Everything else (`streamlit`, `supabase`, `pandas`,
`python-dotenv`) is already in `dashboard/pyproject.toml`.

## 5. How this doesn't touch the backend or T24's future work
- No file under `backend/` changes.
- `dashboard/src/dashboard/__init__.py`'s existing stub is untouched.
- Nothing here writes to `tickets`, `offices`, or `routing_corrections` — T24 owns every write path
  (S02 RULES §3), including the actual status-change/reassign UI this list will eventually link to.

## Verification
1. `cd dashboard; uv sync; uv run pytest` — new tests green.
2. `cd dashboard; uv run streamlit run src/dashboard/app.py` — manual: wrong password rejected,
   correct password (from local `.env`) shows the 16 seeded tickets (T20), filters narrow the list
   correctly, log out returns to the password screen.
3. Confirm `backend/` test suite is unaffected (`cd backend; uv run pytest`) — this ticket touches
   no backend file.

## Not doing in this turn
Not implementing until this plan is reviewed — same pattern as T12/T14–T20.
