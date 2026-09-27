# Plan: T12 — Turn Engine (Groq JSON + Gemini fallback)

Ticket: `docs/TICKETS.md` T12 (owner Dev, depends on T02/T11, done when "Valid JSON").
Spec: `docs/specs/S05-turn-engine.md`.

**Scope: T12 only.** This plan builds `backend/app/turn_engine.py` and its own config/tests. It does
**not** wire the Turn Engine into `POST /message` — that's T18 (S04 §2 step 6), once S06/S07 also
exist. `backend/app/main.py` and `backend/app/routes.py` are not touched here.

**Decisions this plan assumes (already resolved, see S05 DECISIONS D-S05-1…5):**
- GPS-only turns (`text` empty/`None`) skip the LLM entirely and return a passthrough `TurnResult`.
- `TurnResult` carries `service_id`, `fields`, `confirmed` only — no `action` (that's S07's job).
- `confirmed` is forced `false` server-side whenever `session.awaiting_confirmation` is `false`,
  regardless of what the LLM returns.
- Exactly one attempt per provider (Groq, then Gemini) — no internal retry loop.
- Extra/unexpected top-level JSON keys from a provider are ignored, not a structural failure.

**New implementation decisions this plan makes** (S05 deliberately stops at the behavior/contract
level, not HTTP-client mechanics):
- Call Groq and Gemini via raw `httpx` (already a dependency), not their SDKs — one POST each:
  `.../openai/v1/chat/completions` (Groq, `response_format: {"type": "json_object"}`) and
  `.../v1beta/models/{model}:generateContent` (Gemini, `generationConfig.responseMimeType:
  "application/json"`). Matches T07's "no new library unless needed" pattern; both are a single
  POST call, not enough surface to justify an SDK dependency.
- `run_turn(..., providers: Sequence[Provider] | None = None)` — an injectable seam (mirrors T07's
  `create_app(specs_dir=...)`), so tests use fake providers with no network calls and no real API
  keys, instead of adding an httpx-mocking library.
- `GROQ_MODEL` / `GEMINI_MODEL` become **required** env vars, not hardcoded defaults — resolves
  G-S05-2 by making Dev confirm current model ids at build time rather than this plan guessing one.
- `LLM_PROVIDER` defaults to `groq` (resolves G-S05-1 per PROJECT.md §6: "Groq (JSON mode) →
  fallback Gemini Flash"). `.env.example`'s current `LLM_PROVIDER=gemini` sample is fixed as part
  of this ticket — flag it to Lead since S01/PROJECT.md changes get called out per `CLAUDE.md`.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `backend/app/turn_engine.py` | Create | `SessionState`, `Message`, `TurnResult`, `TurnEngineUnavailable`, prompt builder, `GroqProvider`/`GeminiProvider`, `run_turn()` — the S05 deliverable |
| `backend/app/config.py` | Edit | Add `LLMConfig` + `get_llm_config()` (S04 §1: LLM vars become required once T12 lands) |
| `backend/tests/test_turn_engine.py` | Create | Fake-provider unit tests: fallback sequencing, structural validation, GPS shortcut, confirmed-forcing |
| `backend/tests/test_config.py` | Edit | Tests for `get_llm_config()` |
| `.env.example` | Edit | Add `GROQ_MODEL=`, `GEMINI_MODEL=`; fix `LLM_PROVIDER` sample to `groq` |
| `README.md` | Edit | Attribution: Groq API and Google Gemini API (external APIs, even with no new PyPI package) |
| `docs/TICKETS.md` | Edit (last step) | Tick T12 `[x]` once everything below is green |

Not touched: `backend/app/main.py`, `backend/app/routes.py`, `backend/mock/*`,
`backend/app/schemas.py`, `backend/app/service_spec.py`, `backend/tests/contract/*` — T18 wires
`turn_engine` into the real route later; the mock and contract suite have no Turn Engine dependency.

## 2. Steps, in order

**S1 — `backend/app/config.py`: `LLMConfig` + `get_llm_config()`.**
```python
@dataclass(frozen=True)
class LLMConfig:
    primary: Literal["groq", "gemini"]
    groq_api_key: str
    gemini_api_key: str
    groq_model: str
    gemini_model: str

def get_llm_config() -> LLMConfig:
    ...
```
Reads `GROQ_API_KEY`, `GEMINI_API_KEY`, `GROQ_MODEL`, `GEMINI_MODEL` — each required, missing any
one raises `RuntimeError` naming that var (same pattern as `get_allowed_origins`). `LLM_PROVIDER`
optional, default `"groq"`; any value other than `groq`/`gemini` raises `RuntimeError` naming the
var and the bad value.

**S2 — `backend/app/turn_engine.py`: data types.**
`SessionState` (`service_id: str | None`, `collected_fields: dict[str, Any]`,
`awaiting_confirmation: bool`) and `Message` (`role: Literal["citizen", "bot"]`, `text: str`) as
plain dataclasses — no dependency on S06's real `Session` class. `TurnResult` (pydantic,
`service_id: str | None`, `fields: dict[str, Any]`, `confirmed: bool`). Internal `_RawTurnOutput`
(pydantic, `ConfigDict(extra="ignore")`, same three fields, `confirmed` optional defaulting `False`)
— the structural-validation shape from S05 §4/§STRUCTURAL VALIDATION. `TurnEngineUnavailable
(RuntimeError)`. `Provider` as a `typing.Protocol` (`name: str`, `def complete(self, prompt: str) ->
str`).

**S3 — Prompt builder `_build_prompt`.**
```python
def _build_prompt(
    session: SessionState,
    specs: dict[str, ServiceSpec],
    text: str,
    lat: float | None,
    lng: float | None,
    recent_messages: Sequence[Message],
) -> str: ...
```
Pure string function (no I/O — independently unit-testable). Renders, per S05 §BEHAVIOR 2–3: fixed
system instructions; each spec's `service`, `label`, `recognise`, and every field's `name`, `type`,
`required`, and allowed values (`enum.values` / `integer.min,max` / `string.max_length` /
`location.accepts`) — never `question` or `out_of_scope.reply` text; session state
(`service_id`, `collected_fields`, `awaiting_confirmation`); up to 4 `recent_messages` oldest-first;
this turn's `text` and a GPS-presence fact (not a value to extract).

**S4 — `GroqProvider` / `GeminiProvider`.**
Each holds an `httpx.Client(timeout=6.0)` (S05 provider timeout table) and implements
`complete(prompt) -> str`: builds the provider-specific request body, POSTs, raises an internal
`_ProviderError` on timeout, connection error, or non-2xx status; otherwise returns the raw response
text (the JSON string to be parsed by the caller). `default_providers(config: LLMConfig) ->
list[Provider]`, ordered `[primary, fallback]` from `config.primary`.

**S5 — `run_turn()`.**
```python
def run_turn(
    *,
    session: SessionState,
    specs: dict[str, ServiceSpec],
    text: str | None,
    lat: float | None,
    lng: float | None,
    recent_messages: Sequence[Message] = (),
    providers: Sequence[Provider] | None = None,
) -> TurnResult:
    if not text or not text.strip():
        return TurnResult(service_id=session.service_id, fields={}, confirmed=False)

    prompt = _build_prompt(session, specs, text, lat, lng, recent_messages)
    for provider in providers or default_providers(get_llm_config()):
        try:
            raw = provider.complete(prompt)
            parsed = _RawTurnOutput.model_validate_json(raw)
        except (_ProviderError, ValueError, ValidationError):
            continue
        if parsed.service_id is not None and parsed.service_id not in specs:
            continue  # hallucinated service id — structural failure (S05 §5.2)
        confirmed = parsed.confirmed and session.awaiting_confirmation
        return TurnResult(service_id=parsed.service_id, fields=parsed.fields, confirmed=confirmed)

    raise TurnEngineUnavailable("both LLM providers failed")
```
`providers=None` only calls `get_llm_config()` lazily (inside the loop's default), so tests that
inject fake providers never need real env vars.

**S6 — `backend/tests/test_turn_engine.py`.**
Fake `Provider` implementations (plain classes/closures tracking call count, no network):
- `test_gps_only_turn_never_calls_a_provider` — `text=None`, providers that raise `AssertionError`
  if called → result echoes `session.service_id`, `fields={}`, `confirmed=False`.
- `test_primary_success_skips_fallback` — Groq fake returns valid JSON; Gemini fake asserts it's
  never called.
- `test_primary_failure_calls_fallback_once` — Groq fake raises; Gemini fake returns valid JSON →
  result comes from Gemini; both call counts == 1.
- `test_malformed_json_treated_as_failure` — Groq fake returns non-JSON text → Gemini used.
- `test_hallucinated_service_id_treated_as_failure` — Groq fake returns a `service_id` not in
  `specs` → Gemini used.
- `test_both_fail_raises_unavailable_no_third_attempt` — both fakes raise → `pytest.raises
  (TurnEngineUnavailable)`; each called exactly once (D-S05-4).
- `test_extra_json_keys_ignored` — Groq fake returns valid schema plus an extra top-level key →
  parsed successfully, Gemini never called (D-S05-5).
- `test_confirmed_forced_false_when_not_awaiting` — `session.awaiting_confirmation=False`, fake
  provider returns `confirmed: true` → `TurnResult.confirmed is False` (D-S05-3).
- `test_prompt_includes_field_vocabulary_and_recent_messages` — smoke-check on `_build_prompt`
  output: field names from the spec, `collected_fields` values, and recent-message text all appear
  in the built prompt string (not exact-string pinned — content presence only).

**S7 — `backend/tests/test_config.py` additions.**
- Missing each of `GROQ_API_KEY` / `GEMINI_API_KEY` / `GROQ_MODEL` / `GEMINI_MODEL` individually →
  `RuntimeError` naming that var.
- `LLM_PROVIDER` unset → `LLMConfig.primary == "groq"`.
- `LLM_PROVIDER="notaprovider"` → `RuntimeError` naming the var and the bad value.
- Full valid env → `LLMConfig` fields match what was set.

**S8 — `.env.example`.**
Add `GROQ_MODEL=` and `GEMINI_MODEL=` (with a comment: confirm current JSON-capable model id at
setup time). Change `LLM_PROVIDER=gemini # or groq` to `LLM_PROVIDER=groq # or gemini` so the
default matches PROJECT.md §6 and this spec (G-S05-1).

**S9 — `README.md` Attribution.**
Add to the Backend bullet list: Groq API (LLM, JSON mode) and Google Gemini API (LLM fallback),
each linked, next to the existing httpx/PyYAML line.

**S10 — Run the suite and lint.**
`cd backend; uv run pytest` (new tests plus all existing ones — contract, spec, config, main —
green) and `uv run ruff check . && uv run ruff format --check .`.

**S11 — Tick it off.**
`docs/TICKETS.md`: T12 `[x]`, once S10 is green.

## 3. Acceptance coverage

S05's own `ACCEPTANCE` section splits mechanical behavior (this ticket) from extraction-correctness
against real Hindi/Hinglish text (T13, downstream, needs T09's 15 sentences first). T12's tests
cover only the former:

| S05 acceptance item | Covered by |
|---|---|
| GPS-only turn → no provider called | S6 `test_gps_only_turn_never_calls_a_provider` |
| `awaiting_confirmation=False` + "yes" → `confirmed` still `False` | S6 `test_confirmed_forced_false_when_not_awaiting` |
| Groq fails → Gemini called once, same prompt, result returned | S6 `test_primary_failure_calls_fallback_once` |
| Both fail → `TurnEngineUnavailable`, no third attempt | S6 `test_both_fail_raises_unavailable_no_third_attempt` |
| Hallucinated `service_id` → treated as failure, fallback attempted | S6 `test_hallucinated_service_id_treated_as_failure` |
| Scenarios 1/2/3/4/6 (real extraction correctness) | **Not covered here** — needs a live LLM call; T13's job |

## 4. New libraries
None — `httpx` is already a dependency and covers both providers. `README.md` Attribution still
gains two **API** entries (Groq, Gemini) per the hackathon rule, which covers APIs as well as
libraries.

## 5. How existing tests and the mock stay unaffected
`backend/mock/*` and `backend/tests/contract/*` have no Turn Engine dependency and are untouched.
`backend/tests/spec/test_service_spec.py` and `backend/tests/test_main.py` don't import
`app.turn_engine`. New tests live in their own files and use injected fake providers — no real
network calls, no requirement for `GROQ_API_KEY`/`GEMINI_API_KEY` to be set in the test environment.

## Verification
1. `cd backend; uv run pytest` — new tests green, all existing ones unaffected.
2. `cd backend; uv run ruff check . && uv run ruff format --check .` — clean.
3. Manual, optional (needs real keys in `.env`): call `run_turn(...)` with the real
   `default_providers(get_llm_config())` against one sample sentence (e.g. "3 दिन से पानी नहीं आ
   रहा") to sanity-check the prompt and parsing end-to-end before T13's formal 15-sentence pass.
