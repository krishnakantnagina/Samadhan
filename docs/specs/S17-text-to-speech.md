# S17 — Text-to-Speech Reply (Sarvam Bulbul)
Implements: T51 (new — `backend/app/tts.py`, `backend/app/routes.py`, `frontend/app.js`) ·
Depends on: S01 API contract (adds one new endpoint, no change to existing ones), S12 Voice
(sibling module, same provider/vendor relationship, opposite direction) · Version: v1 · Status: Draft

## PURPOSE
Adds a voice **reply**, closing the loop T29 opened (voice *in*) — the citizen can now also *hear*
the bot's `reply_text`, not just read it. Was explicitly out of scope for M1 (PROJECT.md §2 "Not
now": "TTS reply"; S01 §14 Out of Scope: "TTS audio in the response") — this spec is that scope
being deliberately added back, requested directly, not a silent expansion.

## KEY DECISION — a separate, on-demand endpoint, not a field on `MessageResponse`
Two ways to wire this in were considered:
1. Add an `audio_base64`/similar field to `MessageResponse` so every reply already carries its own
   spoken version.
2. A **separate** endpoint, `POST /api/v1/speak`, called only when the citizen taps a speaker icon
   on a specific bubble.

**Chosen: (2).** Reasons:
- **Latency.** The turn loop already has an explicit budget (S04 §5, G-API-4: ASR ~8s + LLM ~6s
  ≈14s before any fallback). Synthesizing speech for every single reply — most of which a citizen
  reading the screen will never listen to — adds real latency to the one path that's already tight,
  for a feature most turns won't use.
- **Cost.** Bulbul v3 is priced per character (₹30/10K chars, live-checked 28 Sep 2026). Generating
  audio for every reply (including ones nobody plays) multiplies cost for no benefit; generating it
  only on tap means you pay only for what's actually heard.
- **No contract change to the existing, already-tested endpoint.** `MessageResponse` (S01 §4.2) is
  depended on by every existing test in `backend/tests/contract/` and the whole T18–T29 build.
  Adding a new, independent endpoint touches none of that; a new field on the existing one is a
  contract change every consumer of `POST /message` has to account for, for a feature only some
  turns use.

## SCOPE
`backend/app/tts.py` (new module): one function, `synthesize(text) -> str` (base64 WAV). A new
route, `POST /api/v1/speak`, in `backend/app/routes.py`. A speaker button added to every bot bubble
in `frontend/app.js`, calling the new endpoint on click and playing the result. Does not touch
`POST /api/v1/message`, `GET /api/v1/status/{id}`, or anything under S12 (ASR is a separate,
already-built module in the opposite direction).

## BEHAVIOR

### 1. Backend: `POST /api/v1/speak`
```
Request:  multipart or JSON? -> JSON, {"text": "<the reply_text a bubble is already showing>"}
Response: 200 {"audio_base64": "<base64 WAV, exactly what Sarvam returned, unmodified>"}
```
1. Validate `text`: 1–1000 chars after trimming (same `TEXT_MIN_LENGTH`/`TEXT_MAX_LENGTH` S01
   already defines — the text being spoken is always a `reply_text` the backend itself generated
   moments earlier, which is already inside that bound; reusing the constant, not inventing a new
   one). Empty/oversized → `400 INVALID_INPUT`, same error shape as every other endpoint (S01 §7).
2. `tts.synthesize(text)`: one call to
   `POST https://api.sarvam.ai/text-to-speech` (`api-subscription-key` header, JSON body:
   `text`, `language_code: "hi-IN"` (fixed — every `reply_text` in this codebase is native
   Devanagari Hindi, never transliterated/Hinglish; Sarvam's own docs note transliterated input
   "significantly reduces output quality" (live-checked 28 Sep 2026), so a fixed `hi-IN` is
   correct, not a simplification that costs anything), `speaker: SARVAM_TTS_SPEAKER`,
   `model: SARVAM_TTS_MODEL`). Timeout ~8s, same budget class as every other external call in this
   project (S04 §5).
3. Sarvam's response is `{"request_id": ..., "audios": ["<base64 wav>"]}` (live-checked 28 Sep
   2026) — `audios[0]` is forwarded to the frontend **unmodified**: no decode/re-encode step, no
   storage write. This is not a citizen's own data (S02's `audio` bucket is for *citizen* recordings,
   S12/T26); a synthesized reply is regenerated on demand and never needs to persist.
4. Failure (timeout, non-2xx, malformed response) → `503 SERVICE_UNAVAILABLE`, same posture as
   every other external-provider call in this codebase (S05/S12's own fallback-exhausted mapping) —
   **no fallback provider** for TTS specifically (D-S17-2), so one failure is the whole failure.

### 2. Frontend: the speaker button
1. Every bot bubble (`appendMessage('bot', text)`) gets a small 🔊 button alongside it.
2. Click → `POST {API_BASE}/api/v1/speak` with that bubble's own text → on success,
   `new Audio('data:audio/wav;base64,' + data.audio_base64).play()`.
3. While loading: the button shows a brief disabled/loading state (not the whole composer —
   `setBusy` is for the citizen's own turn, this is a side action on a past message and must not
   block typing a new one).
4. Failure: the button itself shows a brief inline state (S16 RULES §3's own "never colour alone"
   posture — a changed icon/label, not just a colour flicker) and resets; this never interrupts the
   conversation with a new chat bubble — a failed "listen" tap is not a failed turn.

## RULES
1. `POST /api/v1/speak` is stateless: no `session_id`, no dedupe, no DB write, no relationship to
   `POST /message` beyond both being under `/api/v1`. It cannot create, change, or look up anything.
2. `language_code` is always `hi-IN`, never derived from citizen input or made configurable per
   request — every string this endpoint is ever asked to speak is a backend-authored `reply_text`,
   always Hindi (D-S17-1).
3. No audio is stored — Sarvam's response is forwarded and forgotten, unlike S12's citizen
   recordings which are deliberately kept (PROJECT.md §7/§13 applies to what a *citizen* said, not
   a synthesized reply of something already logged as `reply_text` in `messages.response`).
4. This endpoint has no authentication, matching every other endpoint in this contract (S01 §3) —
   see G-S17-1 for the one real risk that comes with that here specifically.

## ERRORS
| Situation | Result |
|---|---|
| `text` empty or > 1000 chars | `400 INVALID_INPUT` |
| Sarvam times out / errors / malformed response | `503 SERVICE_UNAVAILABLE` — no fallback provider (D-S17-2) |
| Frontend: fetch/network failure | Same `GENERIC_ERROR`-class handling as every other call in `app.js` (T50's fix), scoped to the speaker button only, not a chat bubble |

## OUT OF SCOPE
- Any change to `POST /api/v1/message`'s response shape.
- Caching/reusing a previously-synthesized reply (a citizen re-tapping "listen" re-synthesizes;
  traffic at pilot scale doesn't justify a cache layer yet).
- Autoplay of the bot's reply the moment it arrives — every browser restricts/blocks unprompted
  audio autoplay without a user gesture, and a citizen mid-read may not want audio interrupting
  them; the speaker button is an explicit choice, not automatic (D-S17-3).
- A fallback TTS provider if Sarvam is down (D-S17-2) — matches this feature's own lower stakes
  (a reply is already fully readable as text; losing the *voice* version of it is not losing the
  reply itself, unlike ASR where losing the input is losing the whole turn).
- Rate limiting / abuse protection on the new endpoint beyond the character cap (G-S17-1) —
  PROJECT.md §2 already lists rate limiting under "Not now" project-wide.

## DECISIONS
| # | Decision | Reason |
|---|---|---|
| D-S17-1 | `language_code` fixed to `hi-IN`, never derived from the citizen's own language choice | Every `reply_text` the backend generates is authored in Hindi (checked: every `REPLY_*` constant, every spec `.hi` field, `CONFIRM_PROMPT_HI`) — there is no English reply path to accommodate yet |
| D-S17-2 | No fallback TTS provider | Losing a voice *reply* leaves the citizen with the same text reply they'd have had anyway — much lower stakes than S12's ASR fallback, where failure loses the citizen's actual input |
| D-S17-3 | No autoplay; a per-bubble speaker button only | Browser autoplay restrictions make unprompted audio unreliable anyway, and a citizen already reading the text may not want audio starting on its own |
| D-S17-4 | Sarvam's base64 WAV is forwarded byte-for-byte, no server-side decode/transcode | No reason to touch the bytes — `<audio>`/`Audio()` plays a `data:audio/wav;base64,...` URI directly; decoding and re-encoding would only add latency and a new failure mode for zero benefit |

## OPEN
| ID | Item | Needed by |
|---|---|---|
| G-S17-1 | `POST /api/v1/speak` has no auth (matches S01 §3's existing posture) and accepts arbitrary `text` up to 1000 chars, not tied to a real `reply_text` the backend generated — a bad actor could call it directly to run up Sarvam usage. No worse than every other unauthenticated endpoint already in this contract, but worth Lead/Dev awareness before demo day, not silently assumed safe | Before deploy (shared concern with G-API-5) |
| G-S17-2 | `SARVAM_TTS_SPEAKER` default (`"shubh"`, Sarvam's own documented default, live-checked 28 Sep 2026) is a PROPOSED pick, not confirmed with Lead/Dev by ear — swap freely, it's one env var | Before demo day |

## ACCEPTANCE
| Item | Covered by |
|---|---|
| Tapping the speaker button on a bot reply plays real Hindi speech | §BEHAVIOR 1–2 |
| `POST /message`'s contract is byte-for-byte unchanged | §SCOPE, KEY DECISION |
| Empty/oversized text → `400`, same shape as every other endpoint | §BEHAVIOR 1 step 1 |
| Sarvam failure → `503`, citizen-safe, scoped to the button not the whole chat | §BEHAVIOR 1 step 4, §BEHAVIOR 2 step 4 |
| No audio persisted anywhere | RULES §3 |
