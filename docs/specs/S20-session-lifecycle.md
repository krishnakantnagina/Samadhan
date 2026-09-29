# S20 — Session Lifecycle: cancel / restart / timeout
Implements: T28 (`backend/app/session.py`, `backend/app/routes.py`, tests) · Depends on: S01 (§8, D-A2,
D-A3), S04 (§2 steps 3–4), S05 (`recent_messages`), S06 (`get_or_create_session`,
`get_recent_messages`) · Version: v1 · Status: Approved (option b chosen 29 Sep)

## 1. Why this spec exists
T28's "done when" is *all three work*. The behavior was built inside T14/T18 and unit-tested per
piece, but never verified end to end, and reading the code found one real defect (§3). This spec
pins down what "works" means, fixes the defect, and lists the checks that close T28.

## 2. Required behavior (already specified — restated so it can be tested)

| Trigger | Required result | Owner |
|---|---|---|
| Text is exactly `cancel` (trim, case-insensitive) | `action=cancelled`, Hindi `REPLY_CANCELLED`, `collected_fields={}`, `awaiting_confirmation=false`, `lat/lng=null`, session status `cancelled`. Never reaches the Turn Engine. | S04 §2 step 4 |
| Text is exactly `restart` | `action=ask`, `ask_for=null`, Hindi `REPLY_RESTART`, same clearing (incl. `lat/lng`), status `active`. Never reaches the Turn Engine. | S04 D-S04-5 |
| Same `session_id` used after `cancelled`, `restart` or `submitted` | Starts a fresh complaint normally (S01 §8). | S06 RULES 3 |
| Idle > 30 min | Session resets to defaults under the same `session_id`; the current message is still processed; the citizen sees no error. | S01 D-A2 |
| Command sent as audio (`cancel`/`restart` spoken) | Transcribed, then matched as a command (§5). Same result as typed; the audio row and `transcript` are kept. | S20 §5 |

## 3. The defect: old turns leak into a fresh conversation
`session.get_recent_messages` returns the last 4 `messages` rows for the `session_id` with no
boundary. After a cancel, restart, submit or timeout, the fields are cleared but the next turn's
prompt (S05 "Recent turns") still contains the **previous complaint's** last messages. The LLM can
then re-extract the old issue or location into the new complaint — the exact "session state cleared"
promise of S01 §8 breaking through the prompt instead of the DB.

### Fix (no schema change)
`get_recent_messages` walks the session's messages newest → oldest and stops at the first
**conversation boundary**. Rows past a boundary are not returned. A boundary is any of:

1. **Terminal reply.** A row whose stored `response.action` is `cancelled` or `submitted`. That row
   and everything before it are excluded.
2. **Restart.** A row whose `response.reply_text == REPLY_RESTART`. That row and everything before
   it are excluded (the word "restart" is noise to the model).
3. **Idle gap.** Two consecutive rows more than `SESSION_TIMEOUT_MINUTES` apart: the older row and
   everything before it are excluded. Also, if the newest row is more than 30 minutes older than
   `now`, return `[]` (the session was just reset by `get_or_create_session`).

The limit of 4 still applies after truncation. Fetch enough rows to find a boundary (`limit * 3`,
capped) then truncate.

Why no new column: a `conversation_started_at` column would need a Supabase migration the day before
the freeze (S02, G-T06-1). All three boundaries are derivable from data already stored.

`REPLY_RESTART` is currently defined in `routes.py`. To avoid `session.py` importing `routes.py`
(circular), it moves to `schemas.py` next to `Command`; `routes.py` imports it from there. The
Hindi text does not change, so the mock and contract suite are untouched. (This also partly
addresses G-S04-8.)

## 4. Out of scope
- Writing `status='expired'` (S06 D-S06-4 stands: staleness stays computed live).
- The `message_id` concurrency gap (G-S06-1) — T31.
- Any frontend change.

## 5. Command aliases (decision G-S20-1, option b)
`api.parse_command` is applied to `effective_text` (typed text, or the transcript for audio) **after**
transcription. Normalise: strip, lowercase, drop trailing `. । ! ?`, collapse whitespace. The
**entire utterance** must equal an alias; substrings never match (so "मेरी शिकायत रद्द नहीं हुई" is
not a command).
- CANCEL: `cancel`, `कैंसल`, `कैन्सल`, `रद्द`, `रद्द करो`, `रद्द करें`, `रद्द कीजिए`, `शिकायत रद्द करो`
- RESTART: `restart`, `रीस्टार्ट`, `रिस्टार्ट`, `शुरू से`, `शुरू से शुरू करो`, `फिर से शुरू करो`, `दोबारा शुरू करो`
The list is a constant in `schemas.py`, to be adjusted from real Sarvam transcripts (live check L6).
An empty transcript is still handled first (S01 D-A6) and is never a command.

## ACCEPTANCE

**Automated (pytest, fakes):**
- [x] `get_recent_messages` returns only rows after a `cancelled` reply
- [x] …only rows after a `submitted` reply
- [x] …only rows after a `REPLY_RESTART` reply, and never the restart row itself
- [x] …only rows after an idle gap > 30 min between two rows
- [x] …`[]` when the newest row is > 30 min old
- [x] …unchanged behavior (last 4, oldest first) for a normal unbroken conversation
- [ ] Route test: `cancel` then a normal message → the Turn Engine receives no pre-cancel turns
- [ ] Route test: a stale session's next message is processed (no error) and gets no old history
- [x] `parse_command` matches every alias and rejects substring/sentence cases
- [x] Route test: spoken `कैंसल` and spoken `शुरू से` (transcribe monkeypatched) act as commands, Turn Engine not called, audio path stored, `transcript` returned
- [x] Existing 209 tests and `ruff check .` still pass

**Live, real backend + real Supabase (results go in the build log, honestly):**
- [ ] L6: a real spoken cancel and restart (human through the mic UI) → real Sarvam transcript matches an alias; if not, adjust the alias list from the real transcript
- [x] L1: issue → `cancel` → new message: reply is a fresh `ask`, old issue not carried over
- [x] L2: issue → location → `restart` → new message: fresh `ask`, old GPS/fields gone
- [ ] L3: complete a ticket, reuse the same `session_id` for a new complaint: new complaint starts
      clean and gets a new `SMD-` number
- [x] L4: timeout — after a partial complaint, backdate that session's `last_active_at` and its
      `messages.created_at` by 31 min directly in Supabase, send a message: processed, fresh state,
      no error (waiting 30 real minutes is not practical; state this in the build log)
- [x] L5: `cancel` as the very first message of a brand-new session: `cancelled`, no crash

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S20-1 | Fix leak by truncating history in `get_recent_messages`, not by a new DB column | No migration before freeze; boundaries are derivable from stored rows |
| D-S20-2 | `REPLY_RESTART` moves to `schemas.py` | Avoids a `session` → `routes` import cycle; text unchanged |
| D-S20-4 | Alias match is whole-utterance only | A complaint sentence containing "रद्द" must never cancel a session |
| D-S20-5 | Command check moves after transcription | A spoken command needs its transcript; audio is stored and `transcript` returned like any voice turn |
| D-S20-3 | Timeout live-tested by backdating rows, not waiting | 30 real minutes is impractical; backdating exercises the same code path |

## OPEN
None. G-S20-1 closed: option b (§5).

## 5b. Natural spoken commands (29 Sep 2026, found by the Lead's real test, L6)
A real spoken cancel failed while the button worked. The stored Sarvam transcripts were **"इसको रद्द करें।"** and **"इसे कैंसिल करें।"**:
full sentences with filler words and the spelling "कैंसिल". The exact-alias match (§5) missed both, and the LLM then filed them as
chit-chat ("unable to reply"). Fix in `schemas.parse_command`: after the exact aliases, a short sentence (at most 6 words) made **only**
of cancel words + filler words is CANCEL; one made only of restart words + filler words is RESTART. Any other word breaks the match, so
"रद्द मत करो", "मेरी शिकायत रद्द नहीं हुई" and a sentence carrying both cancel and restart words are never commands (they go to the LLM).
Tests: the two real transcripts, other spellings, and the negative cases. Live (typed, same code path): all four cancel phrasings,
restart, a clean new complaint after a cancel, and both negatives behave as above. **Still not verified:** a fresh real spoken cancel
through the mic after this fix (needs a human), and other Sarvam spellings we have not seen yet: check `messages.transcript` if one fails.
