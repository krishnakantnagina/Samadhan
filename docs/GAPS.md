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
| G-T06-1 | T06 | Free-tier Supabase project pause after 7 days' inactivity (`docs/research/T06-research.md` §5) sits inside the 30 Sep–10 Oct freeze window, when nothing is supposed to touch the product | Lead | Before the freeze (30 Sep) |
| G-T06-2 | T06 | Max signed-URL `expiresIn` ceiling for the `audio` bucket was never found in Supabase's docs; `60`s works empirically. Whoever builds T24 (dashboard audio playback) should pick a real value and confirm it works, not assume a ceiling | Dev/Lead | Before T24 |
| G-S16-1 | S16 | No real spoken-word audio has been tested against Sarvam/Groq Whisper in this project yet — T29's own live verification used a synthetic tone (proved the record→upload→ASR plumbing works, including a real `503` when both providers genuinely failed on it), not real speech, since an AI agent can't physically speak. Needs a human to record one real Hindi/Hinglish sentence through the mic UI and confirm a non-empty transcript comes back | Lead or Dev | Before demo day |

## Closed

| ID | Gap | Resolution |
|---|---|---|
| G-API-6 | `water_supply.yaml` had no fields, so `summary` keys were undefined | Drafted 27 Sep: fields `issue_type`, `location`, `duration_days`, `address_detail` |
| G-PROJ-1 | Team roles disagreed between PROJECT.md and `CLAUDE.md` | `CLAUDE.md` now matches PROJECT.md: Lead + Dev |
| G-T06-0 | T06-research.md Q1: is RLS + no policies alone enough to block anon, or do default grants also need revoking? | Resolved 27 Sep, live-tested against the deployed project: `schema.sql`'s existing `REVOKE ALL ... FROM anon, authenticated` (already written at T03) is what makes it work — confirmed anon gets `401 permission denied`, not a filtered empty result. No spec or code change needed; see `docs/plans/T06-plan.md` build log |
