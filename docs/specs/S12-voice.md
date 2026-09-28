# S12 — Voice
Implements: T26 (`backend/app/voice.py`, `backend/app/routes.py` audio branch) · Used by: T18's
step 1/5 (D-S04-4's temporary `503` is removed here) · Depends on: S01 §4.1 (audio limits), S02
`audio` bucket (T06), PROJECT.md §7/§13 (keep original audio + transcript) · Version: v1 · Status: Draft

## PURPOSE
Turns uploaded audio into a transcript and a stored `audio_path`, so T18's route can feed the
transcript into the Turn Engine exactly like typed text. Resolves S04's placeholder step 5 and
removes D-S04-4's temporary blanket `503` for audio.

## KEY DECISION — no FFmpeg (deviates from PROJECT.md §7's literal wording)
PROJECT.md describes "Audio → FFmpeg (16 kHz mono WAV) → Sarvam ASR". Verified against both
providers' current docs before building this: **neither requires that conversion.**
- Sarvam's `/speech-to-text` accepts WAV, MP3, AAC, OGG, OPUS, MP4/M4A, WebM, FLAC, AMR, WMA directly
  — exactly the four types S01 already accepts (`ACCEPTED_AUDIO_TYPES`).
- Groq's `/audio/transcriptions` (Whisper) accepts FLAC, MP3, MP4, MPEG, MPGA, M4A, OGG, WAV, WebM.

Sending the browser-recorded bytes straight through, unconverted, works for both providers and
removes a whole external binary dependency (FFmpeg install/availability on Railway, subprocess
handling, temp files) for zero functional gain. **Flagged for Lead** since it changes PROJECT.md's
stated architecture — not a business rule, a verified technical simplification (D-S12-1).

Consequence: audio **duration** (≤ 60 s, G-API-8) is not checked — doing so would require decoding,
reintroducing the FFmpeg dependency this decision just removed. `AUDIO_MAX_BYTES` (2 MB, already
enforced in T18) is the practical proxy: a 2 MB cap already bounds duration for compressed
webm/ogg/opus at typical voice bitrates (D-S12-2).

## BEHAVIOR
`transcribe(audio_bytes, content_type, session_id, message_id, *, client=None) -> VoiceResult`
(`transcript: str`, `audio_path: str`):
1. **Upload first, always.** `audio_path = f"{session_id}/{message_id}.{ext}"` (S02 STORAGE;
   extension from `content_type`), uploaded to the `audio` bucket via `client.storage.from_("audio")
   .upload(...)` — happens **before** transcription is attempted, so the original recording is kept
   even if both ASR providers fail (PROJECT.md §7/§13).
2. **Sarvam primary.** `POST https://api.sarvam.ai/speech-to-text`, `api-subscription-key` header,
   multipart `file` + `model=SARVAM_MODEL` + `language_code=unknown` (auto-detect Hindi/Hinglish/
   English) + `mode=transcribe`. Timeout ~8 s (PROJECT.md §7, S04 §5).
3. **Groq Whisper fallback** on any Sarvam failure (timeout/error/malformed response): `POST
   https://api.groq.com/openai/v1/audio/transcriptions`, `model=GROQ_WHISPER_MODEL`
   (`whisper-large-v3-turbo`), same ~8 s budget. One attempt each, no retry (same posture as S05
   D-S05-4).
4. Both failing → `VoiceUnavailable` → S04 maps to `503 SERVICE_UNAVAILABLE`.
5. An empty/unintelligible transcript from either provider is **not** a failure — returned as-is;
   T18's route turns an empty transcript into `action=error` (S01 D-A6), same as it already does for
   other citizen-facing ambiguity.

## CONFIG
`get_voice_config()` in `app/config.py`: `SARVAM_API_KEY`, `SARVAM_MODEL`, `GROQ_WHISPER_MODEL` — all
required once T26 lands (S04 §1 already reserved `SARVAM_API_KEY` for this). `GROQ_API_KEY` is
reused from `get_llm_config()` — same account, different model for a different task.

## OUT OF SCOPE
Audio duration checking (D-S12-2). Speaker diarization, timestamps, translation modes (Sarvam
supports them; not needed here). Any change to `ACCEPTED_AUDIO_TYPES`/`AUDIO_MAX_BYTES` (T18/S01
already own those).

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S12-1 | No FFmpeg; raw browser audio bytes sent directly to both providers | Verified against current Sarvam/Groq docs — both accept all four `ACCEPTED_AUDIO_TYPES` natively; FFmpeg would be a deployment dependency for no functional benefit |
| D-S12-2 | Audio duration (≤ 60 s) is not checked; `AUDIO_MAX_BYTES` (2 MB) is the practical limit | Duration checking needs decoding, which reintroduces the FFmpeg dependency D-S12-1 just removed |
| D-S12-3 | Storage upload happens before transcription is attempted, unconditionally | PROJECT.md §7/§13: original audio is always kept, even if both ASR providers fail |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S12-1 | D-S12-1 (no FFmpeg) is a real deviation from PROJECT.md's stated architecture — flag for Lead to confirm, same as any other PROJECT.md deviation (S01 §13 precedent) | Before T26 ships to demo |
