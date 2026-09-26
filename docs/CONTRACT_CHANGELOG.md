# Contract Changelog

Every change to a file in `docs/contracts/` needs an entry here, in the same commit (S01 §9, rule 7).
Only the Lead changes contracts. Newest first.

Versioning: a compatible addition (new optional response field) bumps the minor version. A rename, removal,
type change or new required request field is **breaking**, bumps the major version, and is avoided after freeze.

## v1.0.0 — 2026-09-27 — pending freeze

Initial contract (S01). The Lead tags `contract-v1.0.0` on approval. Breaking: n/a (first release).

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
