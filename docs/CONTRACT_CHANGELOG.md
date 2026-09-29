# Contract Changelog

Optional notes on contract changes. Not required: we mostly discuss changes in chat.
Either of us can change a contract; adding a line here is a nice-to-have. Newest first.

## v1.0.0 (unchanged version) — 2026-09-29 — S28 multi-department routing

Additive, `CONTRACT_VERSION` stays `1.0.0`; no new endpoint, no request or response shape change.
- `ask_for` may now be `"service"` (clarify / reconfirm the department). It is already a free string, so clients are unaffected.
- `action = out_of_scope` now also carries the fixed information reply (message, optional validated `.gov.in` link line,
  disclaimer; lines separated by `\n`) and the fixed "unable to reply" reply. `reply_text` may therefore contain newlines and one URL.
- `tickets.department` can differ from the department the ticket was created in after an officer reassigns it across departments.

## v1.0.0 (unchanged version) — 2026-09-29 — T28 / S20

Additive clarification, no request/response shape change, `CONTRACT_VERSION` stays `1.0.0`.
- `cancel` / `restart` now also match a fixed Hindi/Hinglish alias set, and match the **transcript** of an audio turn
  (a spoken cancel/restart is a command). Whole-utterance match only. See S20 §5, S01 D-A3.
- `REPLY_CANCELLED` / `REPLY_RESTART` moved into `schemas.py` (text unchanged).

## v1.0.0 — 2026-09-27

Initial contract (S01).

**Endpoints**
- `POST /api/v1/message` — multipart form; one turn (text, audio, and/or location); returns `MessageResponse`.
- `GET /api/v1/status/{complaint_id}` — returns `StatusResponse` (4 fields only).
- `GET /health` — returns `{"status": "ok"}`.

**Models** (`schemas.py`): `ComplaintStatus`, `Action` (6 values), `OfficeLevel`, `Command`, `ErrorCode`, `MessageRequest`,
`Office`, `Ticket`, `MessageResponse`, `StatusResponse`, `HealthResponse`, `ErrorResponse`.

**Shared constants and helpers** (`schemas.py`): limits (`TEXT_*`, `AUDIO_*`, `ACCEPTED_AUDIO_TYPES`), `COMPLAINT_ID_PATTERN`,
`ERROR_STATUS`, `ERROR_REPLY_TEXT`, `normalise_content_type`, `parse_command`, `check_message_inputs`.

**Decisions**: D-A1 to D-A9 (see `S01-api-contract.md` §11). Open items: `docs/GAPS.md` (G-API-1 to G-API-8).

**Aligned in the same change**: `docs/PROJECT.md` §7, §8, §13 and D9 now use the `/api/v1` paths and list
`updated_at` in the status response.

**Mock and tests**: `backend/mock/` (T08) and `backend/tests/contract/`.
