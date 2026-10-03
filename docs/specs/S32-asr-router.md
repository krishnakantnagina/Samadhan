# S32 — Audio reader with load protection (Gemini first)

Code: `backend/app/asr/`, wired in `backend/app/voice.py`. Tests: `backend/tests/test_asr_*.py`, `test_voice.py`.
Status: built, OFF by default (`ASR_PIPELINE=router` turns it on). Measured on 5 real recordings only (see section 1).

## 1. Why
Five recorded turns (local-research/voice-analysis): Sarvam heard "मार्शल" for "मास्टर", "आपकी क्रिया" for something unclear; Gemini
reading the audio itself fixed them (4-6 s per clip, 503/429 on first tries). Whisper returned gibberish for dialect Hindi.
Sarvam returned HTTP 402 (credit) during the test. Decision: Gemini reads first; Sarvam is the fallback; Whisper is not in the chain.

## 2. Request path (per voice turn)
for each provider in `ASR_PROVIDERS`: skip if its breaker is open -> wait up to `ASR_MAX_QUEUE_WAIT` for a rate-limit token -> take a
concurrency slot -> call (retry a transient failure with backoff + jitter, inside `ASR_BUDGET_SECONDS`) -> quality gate.

| Piece | Rule |
|---|---|
| Rate limiter (token bucket) | per provider, `ASR_*_RPM`; waits briefly, else the next provider |
| Circuit breaker | `ASR_BREAKER_THRESHOLD` failed requests in a row -> open; after cooldown ONE probe; permanent error (401/402/403/404) opens for `ASR_PERMANENT_COOLDOWN` |
| Bulkhead | `ASR_MAX_CONCURRENCY` in-flight calls per provider |
| Retry | 429/5xx/timeout/malformed answer, `ASR_MAX_ATTEMPTS`, exponential backoff 0.4 s..2 s with jitter; Retry-After obeyed but capped at 3 s |
| Quality gate | not audible -> empty transcript (app asks to repeat, S01 D-A6); confidence < `ASR_MIN_CONFIDENCE` -> second opinion from the next provider, else empty transcript |
| Failure | nothing worked -> `AllProvidersFailed` -> `VoiceUnavailable` -> 503 (the recording is already stored, D-S12-3) |

Decisions: D-S32-1 keys only in headers, errors never carry a URL or key. D-S32-2 the reader only transcribes (+ plain Hindi); routing stays
with the Turn Engine. D-S32-3 default OFF so deploying this changes nothing. D-S32-4 state (breakers, buckets) is per process.

## 3. Known limits / next phases
- State is in-process: with N server processes the real Gemini quota is shared by N independent limiters (divide `ASR_GEMINI_RPM` by N).
- No queue yet: the request waits while it is read (<= budget). A job queue + workers (accept fast, answer by push/poll) is phase 2.
- Metrics are in memory (`router.metrics.snapshot()`); no endpoint, dashboard or alert yet.
- `plain_hindi` is returned but not stored or shown to officers yet (no schema change in this slice).
- `context` (last bot question) is supported by `transcribe(..., context=)` but `routes.py` does not pass it yet.
- Gemini needs the PAID tier / Vertex AI for citizen voice (privacy, quota); consent + retention text for voice still to write.
- Accuracy unproven: 5 clips, ground truth not yet confirmed by the Lead. Turn 2 read as "डीपी" with the first prompt and "पुलिया" with the glossary prompt.

## 4. Spoken replies (TTS fallback), added the same day
`backend/app/tts.py`: `TTS_PROVIDERS=sarvam,gemini` adds Gemini speech after Sarvam (default stays Sarvam only, D-S17-2 unchanged).
Sarvam ran out of credit (402) and every `/speak` returned 503; with the fallback `/speak` answered 200 in ~5-6 s with a valid 24 kHz WAV.
Gemini returns raw PCM; it is wrapped into WAV so the website plays it unchanged. A breaker skips a dead provider (402/401/403/404 or
missing config = 5 min, anything else = after 3 failures for 30 s). Checked by transcribing the generated audio with Gemini: it spoke exactly
the Hindi sentence, no English, normal pace, not distorted. Voice quality for citizens is a judgement call: Lead to listen.
Open: Sarvam TTS now answers 400 (not 402) from this server: check TTS model/speaker values in .env against Sarvam's current docs.
