# Contract Changelog

Optional notes on contract changes. Not required: we mostly discuss changes in chat.
Either of us can change a contract; adding a line here is a nice-to-have. Newest first.

## v1.0.0 — 2026-09-27

Initial contract (S01).

**Endpoints**
- `POST /api/v1/message` — multipart form; one turn (text, audio, and/or location); returns `MessageResponse`.
- `GET /api/v1/status/{complaint_id}` — returns `StatusResponse` (4 fields only).
- `GET /health` — returns `{"status": "ok"}`.

**Models** (`api.py`): `ComplaintStatus`, `Action` (6 values), `OfficeLevel`, `Command`, `ErrorCode`, `MessageRequest`,
`Office`, `Ticket`, `MessageResponse`, `StatusResponse`, `HealthResponse`, `ErrorResponse`.

**Shared constants and helpers** (`api.py`): limits (`TEXT_*`, `AUDIO_*`, `ACCEPTED_AUDIO_TYPES`), `COMPLAINT_ID_PATTERN`,
`ERROR_STATUS`, `ERROR_REPLY_TEXT`, `normalise_content_type`, `parse_command`, `check_message_inputs`.

**Decisions**: D-A1 to D-A9 (see `API_SPEC.md` §11). Open items: `docs/GAPS.md` (G-API-1 to G-API-8).

**Aligned in the same change**: `docs/PROJECT.md` §7, §8, §13 and D9 now use the `/api/v1` paths and list
`updated_at` in the status response.

**Mock and tests**: `backend/mock/` (T08) and `backend/tests/contract/`.
