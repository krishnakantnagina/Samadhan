# S13 — Dashboard: Auth, Ticket List, Filters
Implements: T23 (`dashboard/src/dashboard/`) · Depends on: S02 DB schema (`tickets`, `offices`),
PROJECT.md §5/§8 (dashboard reads/writes DB directly, never calls the core) · Version: v1 · Status:
Draft

## PURPOSE
The officer-facing entry point: a shared-password gate, then a filterable, read-only list of
tickets. This is the dashboard's first slice — T24 (detail view, status change, reassign, review
queue) and T30 (map) are separate, later tickets and get their own specs when picked up; nothing
here should be read as describing them in advance.

## SCOPE
`dashboard/src/dashboard/`: `app.py` (entry point, resolves PROJECT.md §11's open "entry file name"
item — `streamlit run src/dashboard/app.py`), `config.py` (env), `db.py` (Supabase client), and
`tickets.py` (the one query T23 needs). Read-only: this ticket never writes to `tickets` or any
other table (S02 RULES §3 reserves writes for T24). Single shared password, no per-officer accounts
or per-department access (PROJECT.md §2 "Not now").

## AUTH

| Rule | Detail |
|---|---|
| Mechanism | One shared secret, `DASHBOARD_PASSWORD` env var (already named in PROJECT.md §8, missing from `.env.example` until this ticket) |
| Check | `secrets.compare_digest(entered, DASHBOARD_PASSWORD)` — constant-time compare, trivial to add, no reason not to |
| State | `st.session_state["authenticated"]`, set on a correct password; Streamlit reruns the whole script on every interaction, so this must persist across reruns within the browser session, not be re-checked every time |
| Scope | Per browser session (Streamlit's own session state), not a durable login — closing the tab logs out. Matches "one shared password," not a real auth system |
| Log out | A sidebar button clears `st.session_state["authenticated"]` — small, expected UX, not scope creep |
| Missing `DASHBOARD_PASSWORD` | App fails fast at startup with a message naming the var (same posture as `backend/app/config.get_allowed_origins`), not a silent "any password works" |

Never log the entered or configured password anywhere (print, `st.write`, exception messages).

## DATA ACCESS

`dashboard/src/dashboard/db.py` mirrors `backend/app/db.py`'s shape exactly (same library, same
posture), but is its own small module — the two are separate `uv` projects with no shared package,
and duplicating five lines is cheaper than introducing one for a hackathon timeline.

```python
@lru_cache
def get_client() -> Client:
    config = get_dashboard_config()
    return create_client(config.supabase_url, config.supabase_service_key)
```

**Service key, not anon key** (PROJECT.md §8: "Service key server-side only (core, dashboard). Anon
key has no access"). `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are the same two vars the backend already
uses — one Supabase project, two server-side consumers, matching PROJECT.md §4's own line: "The
dashboard reads/writes the DB directly, only displays stored data, and never calls the core."

## BEHAVIOR (T23)

### 1. Fetch
One query, no pagination in M1 (row counts are small — 16 today, T05/T20-scale for the pilot):
```python
def list_tickets(*, client: Client | None = None) -> list[dict]:
    client = client or get_client()
    return (
        client.table("tickets")
        .select("complaint_id,status,department,summary_en,created_at,updated_at,"
                "offices(office_name,level)")
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    ).data
```
`offices(office_name,level)` is a PostgREST embed over the `tickets.office_id → offices.id` FK —
one query, not N+1. Never `select("*")` (same posture as S11 `get_status`): `fields`,
`original_text`, `lat`/`lng`, `audio_path`, `session_id` are citizen data T23 has no reason to pull
just to list tickets; T24's detail view fetches them separately, by `complaint_id`, only when an
officer opens that ticket.

### 2. Cache
`st.cache_data(ttl=30)` around the fetch. Streamlit reruns the whole script on every widget
interaction (a filter change, a click); without caching, each of those would re-hit Supabase for no
reason. Filtering itself happens in-memory (pandas) on the cached rows, not as separate queries per
filter — one fetch serves every filter combination for 30 seconds, then refreshes.

### 3. Filters
All computed from the fetched rows, not hardcoded (matches S03's "new service = new YAML file, no
code change" ethos — a second department must not require new filter code):
- **Status** — multiselect, options = the distinct `status` values present, default = all selected.
- **Department** — selectbox, options = "All" + distinct `department` values present.
- **Office** — selectbox, options = "All" + distinct `offices.office_name` values present (depends
  on the department filter: only that department's offices are offered, once one is picked).
- **Search** — a text input matched against `complaint_id` (case-insensitive substring), for an
  officer who already has an ID in hand.

### 4. Display
`st.dataframe` (or `st.table`), one row per ticket, newest first, columns: complaint ID, status,
department, office, English summary, created, last updated. `needs_review` rows get a visibly
distinct treatment (a coloured badge/text, not colour alone — PROJECT.md's own accessibility bar
from the pitch deck's design pass applies here too) so an officer scanning the list doesn't have to
read every status cell closely to spot one.

## RULES
1. Read-only. No `st.button` here writes to any table — T24 owns every write (S02 RULES §3).
2. Never fetch or display `fields`, `original_text`, `lat`/`lng`, `audio_path`, or `session_id` in
   the list view — those are per-ticket detail (T24), not list-scan data, and some are citizen data
   with no reason to be on screen by default.
3. Filters are derived from data, never a hardcoded department/status list.
4. `DASHBOARD_PASSWORD` missing at startup → fail fast, name the var, same posture as the backend's
   own required-env-var checks.

## ERRORS
| Situation | Result |
|---|---|
| `DASHBOARD_PASSWORD` not set | App refuses to start, message names the var |
| Wrong password entered | `st.error`, stays on the login screen, no attempt counting/lockout (out of scope for a shared-password M1) |
| Supabase query fails | `st.error` with a short message; do not crash the whole app on a transient DB hiccup |

## OUT OF SCOPE
- Ticket detail view, status changes, reassignment, `routing_corrections`, review queue (T24 — own
  spec later).
- Map (T30 — own spec later).
- Per-officer accounts, per-department access (PROJECT.md §2 "Not now" — not just this ticket's
  scope, the whole event's).
- Pagination (fine at current/expected pilot row counts; revisit only if it becomes a real problem).
- Audio playback / signed URLs (T24/G-T06-2 — needed once detail view exists, not for a list).

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S13-1 | Entry file is `dashboard/src/dashboard/app.py` | Resolves PROJECT.md §11's open item; conventional name, matches `uv run streamlit run src/dashboard/app.py` |
| D-S13-2 | Dashboard UI chrome (labels, buttons) is in English; ticket content (Hindi `original_text`/`fields`, English `summary_en`) is shown as stored | Matches S10 D-S10-2's own reasoning: `summary_en` exists specifically so officers get English; no reason to translate the shell around it |
| D-S13-3 | One 30s `st.cache_data` fetch, filtered in-memory, not a query per filter | Streamlit reruns the whole script per interaction; re-querying Supabase on every checkbox click is wasted load for no freshness benefit at this data volume |
| D-S13-4 | `secrets.compare_digest` over `==` for the password check | Zero-cost, standard practice; not pretending this is a real auth system otherwise |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S13-1 | `DASHBOARD_PASSWORD` needs an actual value chosen and shared between Lead/Dev (never committed) — add to local `.env` only | Before either of you runs the dashboard |

## ACCEPTANCE
| Item | Covered by |
|---|---|
| TICKETS.md "Tickets listed" | §BEHAVIOR 1, 4 |
| Wrong password → no access | §AUTH, §ERRORS |
| Missing `DASHBOARD_PASSWORD` → fails at startup, names the var | §AUTH, §RULES 4 |
| Filters reflect real data, not a hardcoded department | §BEHAVIOR 3, §RULES 3 |
| No citizen-only fields (`fields`, `original_text`, `lat`/`lng`) fetched or shown | §BEHAVIOR 1, §RULES 2 |
