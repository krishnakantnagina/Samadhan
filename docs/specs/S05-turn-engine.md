# S05 — Turn Engine (Groq JSON + Gemini Fallback)
Implements: T12 (`backend/app/turn_engine.py`) · Used by: T18 (S04 §2 step 6) · Depends on: S01 API contract (`action`, `summary`), S03 service spec format, S04 orchestration (calling contract, error mapping, timeouts) · Version: v1 · Status: Draft

## PURPOSE
One LLM call per citizen turn that turns free-form Hindi/Hinglish text into structured, **untrusted**
data: which loaded service the text matches (if any), what field values the citizen gave or implied,
and whether this turn confirms a previously shown summary. The backend never trusts this output on
its own — S07 (Validator) checks every field against the service spec before anything is stored or
shown (PROJECT.md §4 principle 2 / S01 §2 principle 2).

## SCOPE
`backend/app/turn_engine.py` (T12): prompt construction, the Groq call, the Gemini fallback call, and
structural validation of the JSON response. It does **not** decide the citizen-facing `action`, does
**not** validate field values against spec type rules (enum/min/max/length — S07), does **not**
resolve jurisdiction (S09/S10), and does **not** touch the database. M1 loads one service
(`water_supply`); the interface takes `dict[str, ServiceSpec]` so a second service needs no signature
change (S03 "Adding a service"), even though the prompt strategy for choosing between two is not
designed here (see OUT OF SCOPE).

## INPUT
`run_turn`'s parameters — this spec owns the signature named provisionally in S04 §3:

| Param | Type | Source | Notes |
|---|---|---|---|
| `session` | `SessionState` | S06 Session Manager | Minimal view of a session row (S02): `service_id`, `collected_fields`, `awaiting_confirmation` |
| `specs` | `dict[str, ServiceSpec]` | `app.state.specs` (S03, loaded once at startup) | Every loaded service, not just the active one — needed to detect a service on the citizen's first turn |
| `text` | `str` | S04 §2 step 6: `text or transcript` | Citizen's message this turn, already resolved from text/audio. May be empty on a GPS-only turn (S01 D-A8) |
| `lat`, `lng` | `float \| None` | S04 §2 step 1 | Context only. Never extracted by the LLM — S03: GPS is stored directly in `tickets`/`sessions` `lat`/`lng`, never through a spec `fields` value |
| `recent_messages` | `Sequence[Message]` | S06 / `messages` table (S02) | Up to the last 4 rows for this session, oldest first (PROJECT.md §4) |

`SessionState` (`service_id: str | None`, `collected_fields: dict[str, Any]`,
`awaiting_confirmation: bool`) and `Message` (`role: "citizen" | "bot"`, `text: str`) are minimal
structures this module defines. S06 must produce values matching this shape, whatever its own
internal `Session` class looks like — S05 does not depend on S06's implementation.

## OUTPUT
`TurnResult`: `service_id: str | None`, `fields: dict[str, Any]`, `confirmed: bool`.

- **`service_id`** — the key of `specs` the LLM matched, or `None` for "matches no loaded service"
  (S07 maps `None` to `action = out_of_scope`, S04 §2 step 7).
- **`fields`** — only the field(s) the citizen gave or changed **this turn**, keyed by the spec
  field's `name`. Never the full `collected_fields` echoed back. Raw and untrusted: S07 drops
  anything not in the spec, or failing its type rule (S03 TURN RULES #4).
- **`confirmed`** — `true` only when `session.awaiting_confirmation` was `true` **and** the LLM read
  this turn as an affirmation of the shown summary, not a correction. S05 forces this to `false`
  whenever `session.awaiting_confirmation` is `false`, regardless of what the LLM returns (defense in
  depth — PROJECT.md §4: "LLM output is always validated with Pydantic").

Raises `TurnEngineUnavailable` when both providers fail (§ PROVIDERS AND FALLBACK) — S04 maps this to
`503 SERVICE_UNAVAILABLE` (S04 §4).

## BEHAVIOR

### 1. GPS-only turns skip the LLM
If `text` is empty or `None` after trimming, S05 calls no provider. It returns
`TurnResult(service_id=session.service_id, fields={}, confirmed=False)` immediately. GPS carries no
service or field intent by itself (S03: the location field's GPS form is passed straight through to
jurisdiction resolution, not extracted from text), so spending an LLM call and its ~6 s budget on it
would only add latency and a new failure mode for no benefit. This is the path scenario 7 (S01
§10.2) takes to `submitted` after a location-button tap.

### 2. Prompt construction
One prompt per call, sent verbatim to whichever provider is tried. Built from:
1. **System instructions** (fixed, not templated per turn) — see §3 below.
2. **Loaded services** — for each spec in `specs`: `service` id, `label`, `recognise` hints, and
   every field's `name`, `type`, `required`, and type-specific allowed values (`enum.values`,
   `integer.min`/`max`, `string.max_length`, `location.accepts`). This is the **only** vocabulary the
   LLM may use in its `fields` output. `question` text and `out_of_scope.reply` are **not** included —
   those are citizen-facing copy owned by S07/S04, not inputs to extraction.
3. **Session state** — `session.service_id` (or "none yet"), `session.collected_fields` (so the LLM
   does not re-extract or contradict what is already stored), `session.awaiting_confirmation`.
4. **Recent turns** — up to 4 `recent_messages`, oldest first, rendered as alternating citizen/bot
   lines.
5. **This turn** — `text`, and whether `lat`/`lng` are present, stated as a fact (e.g. "the citizen
   also just shared their GPS location") — not as something to extract.

### 3. System instructions (content, not literal prompt text)
- Output **only** JSON matching the schema in §4. No prose, no markdown fences.
- `service_id` must be one of the listed service ids, or `null` if the citizen's message matches none
  of them (PROJECT.md §4: never invent a service).
- `fields` keys must be field `name`s from the matched service's spec only, and only for fields the
  citizen actually gave or changed this turn — never repeat what "session state" already lists as
  collected; never invent a field or a value outside its listed allowed values.
- `confirmed` is `true` only if `session.awaiting_confirmation` is true **and** this turn plainly
  affirms the summary (e.g. "haan", "yes", "sahi hai", "theek hai") with no correction in it. A
  correction (a new/changed field value) is `confirmed: false` even if phrased politely.
- If the message reads as unrelated to every listed service, set `service_id: null` and leave
  `fields` empty — never guess the closest service.
- Never put a citizen's raw location text into `fields` unless the matched service has a `location`
  field expecting a place name (S03) — and even then, only the place name, not commentary.

### 4. Output JSON schema
```json
{
  "service_id": "water_supply | null",
  "fields": { "<field_name>": "<value>" },
  "confirmed": true
}
```
Both providers are called in a mode that constrains output to JSON (Groq JSON mode; Gemini
`response_mime_type: application/json`). This reduces, but does not remove, the need for the
structural validation below.

## PROVIDERS AND FALLBACK

| Provider | Role | Timeout | Model |
|---|---|---|---|
| Groq | Primary | ~6 s (S04 §5) | `[DECIDE]` — confirm the current Groq JSON-mode model at implementation time; `GROQ_MODEL` env var, no model id fixed by this spec |
| Gemini Flash | Fallback | ~6 s (S04 §5), same budget as primary | `[DECIDE]` — confirm the current Gemini Flash model id; `GEMINI_MODEL` env var |

`GROQ_API_KEY` and `GEMINI_API_KEY` become required at import time once T12 lands (S04 §1 already
reserves this). `LLM_PROVIDER` names which one is **primary** — default `groq`, per PROJECT.md §6
("Groq (JSON mode) → fallback Gemini Flash"); the other is always the fallback. See G-S05-1:
`.env.example`'s current sample (`LLM_PROVIDER=gemini`) conflicts with this and needs Lead to confirm
or fix, since PROJECT.md is the source of truth (`CLAUDE.md`).

**Sequence:**
1. Call the primary provider once with the prompt from §2.
2. Primary fails — timeout, non-2xx/connection error, response is not valid JSON, or the JSON fails
   the structural checks below — call the fallback once, same prompt, same timeout.
3. Fallback also fails the same way → raise `TurnEngineUnavailable` (S04 §2 step 6 →
   `503 SERVICE_UNAVAILABLE`). No second retry on either provider: the combined budget is already
   tight (S04 §5, G-API-4 — ~14 s ASR+LLM before any fallback).

## STRUCTURAL VALIDATION
Applied to whichever provider's response is used; a failure here counts as "fails" in the fallback
sequence above, not a citizen-facing `action = error` — both providers failing this check is a
provider/prompt problem, not a citizen input problem (S04 §4 error mapping, step 6).
1. Valid JSON object containing the three keys of §4. Extra top-level keys are **ignored**, not a
   failure (D-S05-5).
2. `service_id` is `null` or a key of `specs` — anything else (a hallucinated service id) fails.
3. `fields` is a JSON object (possibly empty); anything else fails.
4. `confirmed` is a JSON boolean; if missing, treated as `false` (not a failure).

After structural validation passes, S05 applies exactly one more rule before returning: force
`confirmed = False` if `session.awaiting_confirmation` is `False` (§OUTPUT, D-S05-3). Per-field
type/range checking against the spec is S07's job, not S05's (S04 §2 step 7) — nothing else is
normalized here.

## RULES
1. The LLM is given the field vocabulary explicitly (§2.2); it is never asked to guess a schema.
2. S05 never writes to the database, never resolves jurisdiction, and never decides the citizen-facing
   `action` or `reply_text` — those belong to S07 and S04 (S04 §3 interface table).
3. `cancel`/`restart` never reach S05 — S04 §2 step 4 intercepts them before the Turn Engine is
   called (S01 D-A3).
4. A GPS-only turn (§BEHAVIOR 1) never calls a provider.
5. One attempt per provider, no internal retry loop.

## ERRORS
| Situation | Result |
|---|---|
| Primary times out / errors / returns invalid or structurally-invalid JSON | Fallback tried once |
| Fallback also fails the same way | `TurnEngineUnavailable` raised → S04 → `503 SERVICE_UNAVAILABLE` |
| `text` empty/`None` (GPS-only turn) | No provider called; §BEHAVIOR 1 short-circuit, not an error |
| LLM returns a `service_id` not in `specs` | Structural validation failure → counted as a provider failure, not a citizen error |

## OUT OF SCOPE
- Choosing which `out_of_scope.reply` is shown (S07/S04; moot in M1 with one service — S03 OPEN).
- Multi-service disambiguation prompting, for when a second service is loaded (M1 ships one).
- TTS, streaming responses, LLM memory beyond the last 4 messages (PROJECT.md §2 "not now" / §4).
- Prompt-level rate limiting or per-call cost tracking.
- Grading the 15 test sentences (T09/T13) — downstream of this spec, not part of it.

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S05-1 | GPS-only turns skip the LLM entirely (§BEHAVIOR 1) | GPS carries no field/service intent by itself (S03); saves ~6 s and a failure mode for a turn whose answer is already fully determined |
| D-S05-2 | `TurnResult` has no `action` field; only `service_id`, `fields`, `confirmed` | S04 §3 gives the action decision to S07 — keeps "what the citizen said" separate from "what we do about it" |
| D-S05-3 | `confirmed` is forced to `false` server-side when `session.awaiting_confirmation` is `false` | Defense in depth (PROJECT.md §4); a hallucinated or prompt-injected `true` cannot fast-forward a ticket |
| D-S05-4 | Exactly one attempt per provider, no internal retry | S04 §5's combined ASR+LLM budget (~14 s) leaves no room for retries within a single provider |
| D-S05-5 | Extra/unexpected top-level JSON keys are ignored, not a structural-validation failure | Response hygiene isn't a business-rule violation; failing the whole turn over a stray key wastes the fallback budget for no safety benefit |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S05-1 | ~~`.env.example`'s `LLM_PROVIDER=gemini`...~~ — **Closed 28 Sep:** `LLM_PROVIDER=groq` confirmed as the live default, matching PROJECT.md §6 | Closed |
| G-S05-2 | ~~Exact `GROQ_MODEL` / `GEMINI_MODEL` ids~~ — **Re-opened 28 Sep:** `llama-3.3-70b-versatile` was retired from Groq's lineup entirely (`model_not_found`, confirmed via `GET /v1/models`) — this is real model churn, not a one-off. Live-checked replacement: `openai/gpt-oss-120b`, correctly extracts fields from the real Hinglish prompt in ~1.3 s (well under the 6 s budget, and faster than every Gemini timing recorded in G-S05-4). `.env.example` updated. **Re-check again before demo day** — this is now a recurring risk, not a one-time fix | Recheck before demo day |
| G-S05-3 | Multi-service disambiguation prompt design — deferred until a second service exists (S03 OPEN; out of scope here) | Whenever a second service ships (post-M1) |
| G-S05-4 | Live-checked 27 Sep: Gemini's newest flagship models (`gemini-3.7-flash`, `gemini-3.8-flash`) returned `503 Service Unavailable` under load, and even the chosen `gemini-3.6-flash` timed out on 1 of 3 consecutive calls at the 6 s budget (S04 §5). With Groq genuinely working again (G-S05-2) and consistently faster (~1.3–4s vs. Gemini's 4.5–6.7s on the same real prompt), Groq staying primary is the right call, not just the default — Gemini's flakiness is exactly what the fallback exists for. Still worth a closer look in T27 | Before T27 / demo day |

## ACCEPTANCE
Ticket-level acceptance for T12. T13 (prompt tests, ≥ 13/15 on T09's sentences) is separate and
downstream, and needs T09's sentences to exist first.
- [ ] Scenario 1/2 (S01 §10.2): "3 दिन से पानी नहीं आ रहा" (voice or Hinglish text) →
      `service_id = "water_supply"`, `fields` includes `issue_type = no_supply` — no `location` in
      `fields`, since it wasn't given
- [ ] Scenario 3: issue + place in one message → `fields` has both `issue_type` and `location` from a
      single `run_turn` call
- [ ] Scenario 4: at confirmation, a corrected field → `confirmed = False`, `fields` has only the
      corrected field
- [ ] Scenario 6: an unrelated complaint (e.g. electricity, roads) → `service_id = None`,
      `fields = {}`
- [ ] Scenario 7: a GPS-only turn → no provider called (assert via call count), `fields = {}`
- [ ] `session.awaiting_confirmation = False` and the citizen says "yes" → `confirmed` is still
      `False` in the returned `TurnResult` (D-S05-3)
- [ ] Groq forced to fail (mocked) → Gemini is called once with the same prompt and its result is
      returned
- [ ] Both providers forced to fail (mocked) → `TurnEngineUnavailable` is raised, no third attempt
- [ ] A mocked provider response with a `service_id` not in `specs` → treated as a failure, fallback
      attempted
