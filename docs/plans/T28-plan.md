# Plan: T28 — cancel / restart / timeout

Ticket: `docs/TICKETS.md` T28 (owner D, depends on T18 `[x]`, done when "All work").
Spec: `docs/specs/S20-session-lifecycle.md` (option b: spoken commands).

## Context
T28's done-when is "all three work". They exist (T14/T18) but were never verified end to end, and
reading the code found a defect: `session.get_recent_messages` has no conversation boundary, so
after cancel/restart/submit/timeout the previous complaint's last 4 turns still go into the LLM
prompt. Decision made by the user: **option b** — a spoken cancel/restart must also work, so the
transcript (and typed Hindi) is matched against a command alias set. Spec: `docs/specs/S20-session-lifecycle.md`.
Repo convention: spec → plan (`docs/plans/T28-plan.md`, ending in a build log) → implementation → live check.

## Steps (in order)

**S0 — Docs first (no code)**
1. Edit `docs/specs/S20-session-lifecycle.md`: close G-S20-1 as option b; add §5 "Command aliases" (below);
   add acceptance boxes; add D-S20-4 (alias match is whole-utterance only) and D-S20-5 (commands are now
   checked after transcription, so audio is stored and returned with `transcript`); §2 row "Command sent as audio" → command.
2. Amend `docs/specs/S01-api-contract.md` D-A3 (+ §4.1 line 82) and `docs/specs/S04-message-endpoint.md` §2 step 4 (order becomes: transcribe, then command check). Log in `docs/CONTRACT_CHANGELOG.md` (additive; request/response shapes unchanged, so `CONTRACT_VERSION` stays).
3. Write `docs/plans/T28-plan.md` (this plan, in the repo's plan format).

**Command aliases (S20 §5)** — normalise = `strip()`, lowercase, drop trailing `. । ! ?` and collapse spaces; match the
**entire utterance** exactly, never a substring (so "मेरी शिकायत रद्द नहीं हुई" is not a command).
- CANCEL: `cancel`, `कैंसल`, `कैन्सल`, `रद्द`, `रद्द करो`, `रद्द करें`, `रद्द कीजिए`, `शिकायत रद्द करो`
- RESTART: `restart`, `रीस्टार्ट`, `रिस्टार्ट`, `शुरू से`, `शुरू से शुरू करो`, `फिर से शुरू करो`, `दोबारा शुरू करो`
- Alias list is a constant in `schemas.py`; the exact Sarvam spellings get confirmed in the live check (L6) and the list adjusted from real transcripts.

**S1 — `backend/app/schemas.py`**
- Add `REPLY_RESTART`, `REPLY_CANCELLED` (moved from `routes.py`; text unchanged).
- Add `COMMAND_ALIASES: dict[str, Command]` and `_normalise_command_text`; `parse_command` (line 214) uses the alias map. Existing behaviour (`" Cancel "`, `"RESTART"`, `"cancel my complaint"` → None) is preserved.

**S2 — `backend/app/session.py`**
- Rewrite `get_recent_messages` (line 165): select `text,transcript,response,created_at`, fetch `limit*3` newest rows, walk newest→oldest, stop at first boundary (S20 §3: terminal `response.action` cancelled/submitted; `reply_text == schemas.REPLY_RESTART`; gap > `SESSION_TIMEOUT_MINUTES` between consecutive rows; newest row older than now by > 30 min → `[]`); then truncate to `limit`, oldest first, unroll as today.
- Mock/fake: extend `FakeSupabaseClient` rows in `tests/test_session.py` with `created_at` (the fake already orders by `created_at`).

**S3 — `backend/app/routes.py`**
- Import replies from `schemas`; delete local constants (line 26–28).
- Move the command block (lines 111–150) after the audio/transcript step (line 152–190): compute `command = api.parse_command(effective_text)` where `effective_text = text if text is not None else transcript`. Factor the duplicated cancel/restart `MessageResponse`+`SessionUpdate` construction into one helper `_command_turn(command, ...)` (reuses `_persist`), passing `input_type`, `transcript`, `audio_path` through so a spoken command keeps its audio row.
- Empty-transcript branch stays before the command check.

**S4 — Tests (pytest)**
- `tests/test_session.py`: 6 cases from S20 acceptance (after cancelled / submitted / restart / idle gap / newest stale → `[]` / unbroken unchanged).
- `tests/contract/test_api_models.py`: alias cases for `parse_command`, incl. negative substring cases.
- `tests/test_routes.py`: (a) spoken `कैंसल` (monkeypatch `voice.transcribe`) → `cancelled`, Turn Engine not called, audio_path saved, `transcript` in response; (b) same for restart; (c) cancel then normal message → `run_turn` receives `recent_messages == []` (monkeypatch `get_recent_messages` isn't enough; use the real function against the fake, or assert call args); (d) stale session processed with no error.
- Run `cd backend; uv run pytest` (expect 209 + new) and `uv run ruff check .`.

**S5 — Live verification** (real backend :8000 + real Supabase; helper script in the scratchpad, not the repo; fresh `session_id`s)
L1 cancel · L2 restart · L3 session reuse after submit (creates a real `SMD-` ticket — tell the user; delete/mark it afterwards only if they ask) · L4 timeout via backdating `sessions.last_active_at` and `messages.created_at` −31 min · L5 cancel as first message · **L6** spoken cancel/restart: reuse the recorded webm samples in `submission/t09-voice-samples/` only if one contains the word; otherwise ask the user to speak "कैंसल"/"शुरू से" through the mic UI and read back the real transcript from `messages.transcript`. State plainly which items were not verifiable without a human.

**S6 — Close-out**
- Append a build log to `docs/plans/T28-plan.md` (what was verified live vs. not).
- Tick T28 `[x]` in `docs/TICKETS.md` only if L1–L5 pass (L6 human-dependent items noted, as T52 does).
- README Attribution: no new library, nothing to add.
- Update `docs/specs/S06` (get_recent_messages contract) and `docs/specs/S04` acceptance boxes; refresh the stale T28 line in `docs/ONBOARDING.md`.
- Commit only when the user asks (working tree already has the user's staged T09 files — do not sweep them into the T28 commit).

## Files touched
`backend/app/{schemas,session,routes}.py`; tests in `backend/tests/{test_session,test_routes}.py`, `tests/contract/test_api_models.py`; docs `S01`, `S04`, `S06`, `S20`, `CONTRACT_CHANGELOG.md`, `plans/T28-plan.md`, `TICKETS.md`, `ONBOARDING.md`. No frontend, schema.sql or dependency change.

## Risks
- Alias false positives: mitigated by whole-utterance match; list is small and reviewable.
- Sarvam may transcribe "cancel" in a form not in the list → L6 checks it; unknown forms fall back to the LLM (today's behaviour), never a crash.
- Moving the command check after ASR means a spoken command costs one ASR call (~1–3 s) — unavoidable, and the audio is preserved.
- Freeze is tomorrow noon: S1–S4 are small; if time runs short, S2 (the defect) is the priority over S3 (spoken commands).

## Build log (29 Sep 2026)

**Implemented:** S1 `schemas.py` (aliases, `parse_command`, reply constants), S2 `session.get_recent_messages`
boundaries, S3 `routes.py` (command check after transcription, `_command_response`/`_command_update`).
**Tests:** 229 passed (was 209), `ruff check` clean.
**Deviation:** two planned route tests were covered at a lower level instead: "cancel then message gets no old
history" by the `test_history_*` session tests, "stale session processed" by the existing
`test_get_or_create_session_resets_stale`.

**Verified live** (real backend :8000, real Groq, real Supabase, fresh session ids; helper script kept out of the repo):
- L1 cancel, L2 restart, L4 timeout (rows backdated 31 min, not a real 30 min wait): the history handed to the
  LLM was `[]` after each boundary, and the following message was processed with no error and no carried-over state.
- L5 cancel as the first message of a new session: `cancelled`, no crash.
- Weakness: the probe message "कोलार" alone returns `out_of_scope`, so the live runs prove the *history* is empty
  more strongly than they prove the LLM's behaviour would have differed without the fix.

**Not verified:**
- L3 (reuse a session after a submitted ticket): would create a real `SMD-` ticket in the shared Supabase, skipped
  pending the Lead's OK. The submitted-boundary logic is covered by a unit test only.
- L6 (real spoken cancel/restart through Sarvam): needs a human at the mic. The alias list is unverified against real transcripts.
- Live tests left 4 test sessions and their messages in Supabase (no tickets).
