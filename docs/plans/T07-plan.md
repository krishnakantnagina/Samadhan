# Plan: T07 — FastAPI skeleton, config, CORS, `/health`

Ticket: `docs/TICKETS.md` T07 (`backend/app/main.py`, owner Dev, depends on T01/T02, done when "200 OK").
Spec: `docs/specs/S04-message-endpoint.md` §1 "App setup (T07)".

**Scope: T07 only.** No `/message` route body, no Turn Engine/session/validator/ticket/voice
calls — those are T18/T19 (S04 §2–§3) and land once S05/S06/S07/S10/S12 exist. This plan does not
write any of that.

**Decisions this plan assumes (already resolved, see S04 DECISIONS D-S04-1/D-S04-2):**
- `SPECS_DIR` is a fixed path relative to `main.py` (`Path(__file__).resolve().parents[2] / "specs"`), no env var.
- No Supabase/DB client in T07. `/health` never touches the DB (S01 rule 5); nothing else in scope needs one.
- Only `ALLOWED_ORIGINS` is a required env var for T07. `SUPABASE_*`, `GROQ_API_KEY`, `GEMINI_API_KEY`,
  `SARVAM_API_KEY`, `LLM_PROVIDER` stay optional/unread until the ticket that needs them (T14, T12, T26).

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `backend/app/config.py` | Create | Single place for `ALLOWED_ORIGINS` parsing, so it's unit-testable without booting the app (S04 §1 "Config" row) |
| `backend/app/routes.py` | Create | Empty `APIRouter()` mounted at `/api/v1`. T18 adds `POST /message` here, T19 adds `GET /status/{complaint_id}` here — `main.py` itself doesn't change when those land (S04 §1 "Router" row) |
| `backend/app/main.py` | Create | The actual T07 deliverable: app factory, lifespan (spec loading), CORS, error handlers, `/health` |
| `backend/tests/test_config.py` | Create | Unit tests for `config.get_allowed_origins()` |
| `backend/tests/test_main.py` | Create | Tests for `/health`, CORS allowed/blocked, startup spec loading (good + broken) |
| `backend/README.md` | Edit | Add the real-API run command next to the existing mock one, so the file matches what's actually runnable |
| `docs/PROJECT.md` §7 | Edit | Drop the "once it exists" caveat on `app.main:app` now that it does |
| `docs/TICKETS.md` | Edit (last step) | Tick T07 `[x]` once everything below is green |

No file outside `backend/` and the two doc lines above is touched. `backend/mock/`,
`backend/app/schemas.py`, `backend/app/service_spec.py`, and every existing test file are
untouched — see §6.

## 2. Steps, in order

**S1 — `backend/app/config.py`.**
`get_allowed_origins() -> list[str]`: read `os.environ.get("ALLOWED_ORIGINS", "")`, split on `,`,
strip and drop empties — identical logic to `mock/app.py`'s `_origins` line. If the result is
empty, raise `RuntimeError("ALLOWED_ORIGINS is not set")` (names the var, per acceptance). Pure
function, no FastAPI import — testable on its own in S4.

**S2 — `backend/app/routes.py`.**
`router = APIRouter()`. No routes. One-line module docstring: "T18 adds POST /message, T19 adds
GET /status/{complaint_id} here." Nothing to test yet beyond "it imports and mounts" (covered by
S3/S5, not its own test file — an empty router has no behaviour to assert).

**S3 — `backend/app/main.py`.**
```
SPECS_DIR = Path(__file__).resolve().parents[2] / "specs"

def create_app(specs_dir: Path = SPECS_DIR) -> FastAPI:
    origins = config.get_allowed_origins()          # raises before the app object exists

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.specs = service_spec.load_specs(specs_dir)   # raises SpecError -> startup fails
        yield

    app = FastAPI(title="Samadhan API", version=schemas.CONTRACT_VERSION, lifespan=lifespan)
    register_error_handlers(app)                     # reuse from app/errors.py, unchanged
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                        allow_methods=["GET", "POST"], allow_headers=["*"])
    app.include_router(routes.router, prefix="/api/v1")

    @app.get("/health", response_model=schemas.HealthResponse)
    def health() -> schemas.HealthResponse:
        return schemas.HealthResponse()

    return app

app = create_app()
```
Two deliberate choices worth flagging before you approve:
- `create_app()` is a **factory**, not a bare module-level `app = FastAPI(...)` like the mock. This
  is so tests can call `create_app(specs_dir=tmp_path)` for the broken-YAML case and
  `create_app()` with a patched env for the missing-`ALLOWED_ORIGINS` case, without reloading
  modules or touching `sys.modules`. `app = create_app()` at the bottom keeps `uvicorn app.main:app`
  working exactly like the mock's `uvicorn mock.app:app`.
- `specs_dir` is a parameter with the fixed path as its default — production always gets the fixed
  path (matches D-S04-1: no env var), tests override it directly. This isn't a second way to
  configure `SPECS_DIR` in prod, just a seam for S5's broken-spec test.

**S4 — `backend/tests/test_config.py`.**
- `test_missing_raises` — `monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)` → `pytest.raises(RuntimeError, match="ALLOWED_ORIGINS")`.
- `test_blank_raises` — set to `""` or `" , "` → same.
- `test_parses_and_trims` — `"http://a.test, http://b.test"` → `["http://a.test", "http://b.test"]`.

**S5 — `backend/tests/test_main.py`.**
- `test_health_is_ok` — `create_app()` under `TestClient`, `GET /health` → `200`,
  `{"status": "ok"}`, validates against `schemas.HealthResponse`.
- `test_allowed_origin_gets_cors_header` — `monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")`,
  `GET /health` with `Origin: http://localhost:3000` → `access-control-allow-origin` echoes it.
- `test_blocked_origin_gets_no_cors_header` — same app, `Origin: https://evil.example` → header
  absent. (Mirrors `tests/contract/test_health_cors.py`'s two assertions, at the `main.py` level
  instead of the mock.)
- `test_missing_allowed_origins_raises_at_creation` — `monkeypatch.delenv(...)`, `pytest.raises(RuntimeError)` around `create_app()`. Confirms `main.py` actually calls `config.get_allowed_origins()`, not just that the helper works in isolation (S4 already proved that).
- `test_broken_spec_stops_startup` — write one bad YAML file into `tmp_path`, `create_app(specs_dir=tmp_path)`, enter it with `TestClient(...)` as a context manager (triggers `lifespan`) → `pytest.raises(service_spec.SpecError)`.
- `test_real_specs_load_at_startup` — `create_app()` (real fixed `SPECS_DIR`) under `TestClient` as
  a context manager → `app.state.specs` contains `"water_supply"`. Doubles as a regression check
  that `specs/water_supply.yaml` itself still loads.

**S6 — Run the full suite and lint.**
`uv run pytest` (all of `tests/config`, `tests/main`, plus existing `tests/contract`, `tests/spec`
unchanged and green) and `uv run ruff check . && uv run ruff format --check .`.

**S7 — Docs.**
`backend/README.md`: add
```bash
uv run uvicorn app.main:app --port 8000
```
next to the existing mock command. `docs/PROJECT.md` §7: change the comment "real API is
`app.main:app` once it exists" to just state the command, since it now exists.

**S8 — Tick it off.**
`docs/TICKETS.md`: T07 `[x]`, once S6 is green.

## 3. Acceptance coverage (S04 §1 + TICKETS.md)

| Acceptance item | Satisfied by (code) | Verified by (test) |
|---|---|---|
| TICKETS.md: "200 OK" | S3 (`/health` route) | S5 `test_health_is_ok` |
| S04: `main.py` boots and serves `GET /health` with no DB/LLM/ASR calls, matching S01 §6 | S3 (no DB/LLM/ASR client exists in T07's code at all — satisfied by absence, not a mock) | S5 `test_health_is_ok` |
| S04: A broken `specs/*.yaml` stops startup, not the first request | S3 (`lifespan` calls `load_specs` before `yield`) | S5 `test_broken_spec_stops_startup` + `test_real_specs_load_at_startup` |
| S04: Missing `ALLOWED_ORIGINS` stops startup with a message naming the var | S1 (`get_allowed_origins` raises) + S3 (`create_app` calls it before building the app) | S4 `test_missing_raises` + S5 `test_missing_allowed_origins_raises_at_creation` |
| (Implicit in "config, CORS" done-when) CORS allows only listed origins | S3 (`CORSMiddleware` from `get_allowed_origins()`) | S5 `test_allowed_origin_gets_cors_header` + `test_blocked_origin_gets_no_cors_header` |

Every S04 §"ACCEPTANCE" bullet listed under **T07** is covered above. The T18-labelled bullets in
that same section (contract suite against `CONTRACT_TARGET=real`, dedupe, cancel/restart,
LLM-down `503`, dropped invalid field) are out of scope here — they need `/message`, which doesn't
exist until T18.

## 4. Tests to write

| File | Checks |
|---|---|
| `backend/tests/test_config.py` | Missing/blank `ALLOWED_ORIGINS` raises `RuntimeError` naming the var; a valid comma-separated value parses and trims correctly |
| `backend/tests/test_main.py` | `/health` returns `200 {"status":"ok"}` and validates against `schemas.HealthResponse`; an allowed `Origin` gets echoed back in `access-control-allow-origin`; a non-allowed `Origin` gets no CORS header; `create_app()` raises when `ALLOWED_ORIGINS` is missing; startup raises `SpecError` on a broken spec directory; startup succeeds and populates `app.state.specs` with the real `specs/` directory |

Both files live in `backend/tests/` (not `tests/contract/`, which is specifically the shared
mock/real contract suite owned by S01 — T07 has no contract-level behaviour yet, just app
plumbing). `pyproject.toml`'s `testpaths = ["tests"]` picks them up automatically; no config change.

## 5. New libraries

None. Everything used (`fastapi`, `starlette`'s `CORSMiddleware`, `pyyaml` via
`app.service_spec`) is already in `backend/pyproject.toml` from T02/T07-prep/T11. No
`README.md` attribution section change needed for this ticket.

## 6. How the existing mock and tests keep working

- `backend/mock/app.py` and `backend/mock/errors.py` are not touched. `backend/app/main.py` reuses
  `register_error_handlers` from `app/errors.py` the same way the mock already does — no fork, no
  duplicate error-handling logic.
- `backend/tests/contract/*` continues to import `from mock.app import app` (see
  `contract/conftest.py`) and is unaffected — it doesn't know `app.main` exists yet. It only starts
  exercising the real app once T18/T19 add `/message` and `/status/{complaint_id}` to
  `app/routes.py` and someone runs the suite with `CONTRACT_TARGET=real` (S04's own acceptance
  list, not this ticket's).
- `backend/tests/spec/test_service_spec.py` tests `app.service_spec` directly and doesn't import
  `app.main` — unaffected.
- New tests use `TestClient` in-process (no port binding), so they can't collide with anything
  already running, and they don't share fixtures with `tests/contract/conftest.py` (different
  directory, pytest scopes conftest by directory).

## Verification

1. `cd backend; uv run pytest` — new tests plus all existing ones green.
2. `cd backend; uv run ruff check . && uv run ruff format --check .` — clean.
3. `cd backend; uv run uvicorn app.main:app --port 8000` then `curl http://localhost:8000/health`
   → `{"status":"ok"}`, and confirm `uv run uvicorn mock.app:app --port 8001` still runs side by
   side unaffected.
4. Delete/rename `specs/water_supply.yaml` locally for a manual smoke test that startup fails
   loudly (then restore it) — belt-and-suspenders on top of the automated `tmp_path` test.
