# Spec Gaps

> Optional scratchpad of open questions. We mostly discuss in chat; note something here if it helps us remember.

## Open

| ID | Spec | Gap | Owner | Needed by |
|---|---|---|---|---|
| G-API-1 | S01 | Confirm audio limits: ≤ 60 s and ≤ 2 MB (`AUDIO_MAX_SECONDS`, `AUDIO_MAX_BYTES` in `schemas.py`) | Lead | 27 Sep |
| G-API-2 | S01 | Confirm location-only turns (D-A8) and `mp4` audio for Safari (D-A9) | Lead | 27 Sep |
| G-API-3 | S01 | Should `needs_review` be shown to citizens on `GET /status`? It is an internal triage flag; returned as-is today to match PROJECT.md §8 | Lead | 28 Sep |
| G-API-4 | S01 | Client timeout and latency budget: ASR ~8 s + LLM ~6 s already reaches ~14 s before any fallback | Lead + Dev | 28 Sep |
| G-API-5 | S01 | `ALLOWED_ORIGINS` value for the deployed website, and the prod base URL | Lead | Before deploy (29 Sep) |
| G-SPEC-1 | water_supply | Dev to confirm `specs/water_supply.yaml`: the 5 `issue_type` values, required fields (`issue_type`, `location`), and the PROPOSED `max_match_distance_km: 5` for GPS-to-ward matching | Dev | 27 Sep |
| G-API-7 | S01 | Dialect claims and ASR language codes wait for ASR testing (PROJECT.md §21) | Dev | After ASR tests |
| G-API-8 | S01 | Audio duration (≤ 60 s) cannot be checked by the mock; the real backend needs a way to measure it (e.g. `ffprobe` after FFmpeg conversion) and must return `413 AUDIO_TOO_LARGE` | Dev | Before voice ticket |

## Closed

| ID | Gap | Resolution |
|---|---|---|
| G-API-6 | `water_supply.yaml` had no fields, so `summary` keys were undefined | Drafted 27 Sep: fields `issue_type`, `location`, `duration_days`, `address_detail` |
| G-PROJ-1 | Team roles disagreed between PROJECT.md and `CLAUDE.md` | `CLAUDE.md` now matches PROJECT.md: Lead + Dev |
