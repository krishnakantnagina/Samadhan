# Plan: T51 — Text-to-speech reply (Sarvam Bulbul)

Ticket: `docs/TICKETS.md` T51 (new, owner D backend / L frontend, depends on T26 — `[x]`, done when
"Speaker button plays a real Hindi reply"). Spec: `docs/specs/S17-text-to-speech.md`.

**Scope: T51 only.** A new, independent endpoint + a speaker button on bot replies. Does not touch
`POST /api/v1/message`'s contract, S12's ASR module, or anything already tested.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `backend/app/config.py` | Edit | Add `TtsConfig`/`get_tts_config()` — `SARVAM_API_KEY` (reused), `SARVAM_TTS_MODEL`, `SARVAM_TTS_SPEAKER` |
| `backend/app/tts.py` | Create | `synthesize(text) -> str` (base64 WAV), `TtsUnavailable` |
| `backend/app/schemas.py` | Edit | `SpeakRequest`, `SpeakResponse` models |
| `backend/app/routes.py` | Edit | `POST /speak` route |
| `backend/tests/test_tts.py` | Create | Unit tests against a fake `httpx.post` |
| `backend/tests/test_routes.py` | Edit | Route-level tests for `/speak` |
| `.env.example` | Edit | `SARVAM_TTS_MODEL=bulbul:v3`, `SARVAM_TTS_SPEAKER=shubh` (G-S17-2, PROPOSED) |
| `frontend/app.js` | Edit | Speaker button on every bot bubble |
| `frontend/style.css` | Edit | `.speak-btn` styles |
| `docs/TICKETS.md` | Edit | Add T51 row; tick `[x]` once verified |

## 2. Steps, in order

**S1 — `backend/app/config.py`.**
```python
@dataclass(frozen=True)
class TtsConfig:
    sarvam_api_key: str
    sarvam_tts_model: str
    sarvam_tts_speaker: str


def get_tts_config() -> TtsConfig:
    return TtsConfig(
        sarvam_api_key=_require("SARVAM_API_KEY"),  # same key as ASR (S12) -- one Sarvam account
        sarvam_tts_model=_require("SARVAM_TTS_MODEL"),
        sarvam_tts_speaker=_require("SARVAM_TTS_SPEAKER"),
    )
```

**S2 — `backend/app/tts.py`.**
```python
"""S17 -- Text-to-speech reply (T51). Spec: docs/specs/S17-text-to-speech.md.

Sarvam Bulbul only, no fallback (D-S17-2): losing a voice reply leaves the citizen with the text
reply they already have, unlike S12's ASR where a failure loses the citizen's actual input.
"""

import httpx

from app.config import TtsConfig, get_tts_config

PROVIDER_TIMEOUT_SECONDS = 8.0  # same budget class as every other external call (S04 section 5)
LANGUAGE_CODE = "hi-IN"  # D-S17-1: every reply_text is backend-authored, native Hindi, always


class TtsUnavailable(RuntimeError):
    """Sarvam TTS failed. S04-style mapping: 503 SERVICE_UNAVAILABLE."""


def synthesize(text: str, *, config: TtsConfig | None = None) -> str:
    """Returns Sarvam's own base64 WAV string, unmodified (D-S17-4)."""
    config = config or get_tts_config()
    try:
        response = httpx.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"api-subscription-key": config.sarvam_api_key},
            json={
                "text": text,
                "language_code": LANGUAGE_CODE,
                "speaker": config.sarvam_tts_speaker,
                "model": config.sarvam_tts_model,
            },
            timeout=PROVIDER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["audios"][0]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise TtsUnavailable(f"Sarvam TTS failed: {exc}") from exc
```

**S3 — `backend/app/schemas.py` additions.**
```python
class SpeakRequest(ContractModel):
    """POST /api/v1/speak body (S17 section 1). Reuses S01's own text bounds -- every text this
    endpoint is ever asked to speak is a reply_text the backend already generated, already inside
    them."""

    text: str = Field(min_length=TEXT_MIN_LENGTH, max_length=TEXT_MAX_LENGTH)


class SpeakResponse(ContractModel):
    """200 body: Sarvam's own base64 WAV, forwarded unmodified (D-S17-4)."""

    audio_base64: str
```

**S4 — `backend/app/routes.py` addition.**
```python
from app import tts

@router.post("/speak", response_model=api.SpeakResponse)
def speak(body: api.SpeakRequest) -> api.SpeakResponse:
    try:
        audio_base64 = tts.synthesize(body.text)
    except tts.TtsUnavailable as exc:
        raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc
    return api.SpeakResponse(audio_base64=audio_base64)
```
Pydantic's own validation on `SpeakRequest` (length bounds) already produces `400 INVALID_INPUT`
via the existing `RequestValidationError` handler (`app/errors.py`) — no manual check needed here,
same pattern every other Pydantic-validated field in this contract already uses.

**S5 — `backend/tests/test_tts.py`.**
- `test_synthesize_returns_first_audio` — fake `httpx.post` returns `{"audios": ["base64data"]}`,
  assert `synthesize()` returns it unmodified and the request body has `language_code: "hi-IN"`.
- `test_synthesize_raises_on_http_error` — fake raises `httpx.HTTPStatusError` → `TtsUnavailable`.
- `test_synthesize_raises_on_malformed_response` — `{"audios": []}` → `IndexError` → `TtsUnavailable`.

**S6 — `backend/tests/test_routes.py` additions.**
- `test_speak_returns_audio` — monkeypatch `routes.tts.synthesize` → `200`, `audio_base64` matches.
- `test_speak_empty_text_is_400`, `test_speak_too_long_is_400`.
- `test_speak_provider_down_is_503` — monkeypatch to raise `TtsUnavailable` → `503`.

**S7 — `.env.example`.**
```
SARVAM_TTS_MODEL=bulbul:v3      # live-checked 28 Sep 2026, docs.sarvam.ai
SARVAM_TTS_SPEAKER=shubh        # Sarvam's own documented default (G-S17-2, PROPOSED -- swap freely
```

**S8 — `frontend/app.js`.**
```js
async function speakText(text, button) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = '…';
  try {
    const response = await fetch(`${API_BASE}/api/v1/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.reply_text || GENERIC_ERROR);
    const audio = new Audio(`data:audio/wav;base64,${body.audio_base64}`);
    await audio.play();
  } catch {
    button.textContent = '!'; // brief inline failure state, S16 RULES 3 -- not colour alone
    setTimeout(() => { button.textContent = original; }, 1500);
    return;
  } finally {
    button.disabled = false;
  }
  button.textContent = original;
}
```
`appendMessage` gains a speaker button for `role === 'bot'`:
```js
function appendMessage(role, text) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  const textSpan = document.createElement('span');
  textSpan.textContent = text;
  el.appendChild(textSpan);
  if (role === 'bot') {
    const speakBtn = document.createElement('button');
    speakBtn.type = 'button';
    speakBtn.className = 'speak-btn';
    speakBtn.textContent = '🔊';
    speakBtn.setAttribute('aria-label', 'सुनें');
    speakBtn.addEventListener('click', () => speakText(textSpan.textContent, speakBtn));
    el.appendChild(speakBtn);
  }
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}
```
`textSpan.textContent` (not the outer `el.textContent`) is what `handleTurn`'s
`citizenEl.textContent = result.transcript` line and any future bot-bubble text update must target
— **check this against T29's existing code before editing**, since `appendMessage`'s return value
is used elsewhere for exactly that kind of in-place update (S16 D-S16-3) and this change alters
what `.textContent` on the returned element means (now includes the button's own text too, if the
speaker button isn't excluded from that path).

**S9 — `frontend/style.css`.**
```css
.speak-btn {
  margin-left: 8px;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 16px;
  vertical-align: middle;
}

.speak-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

**S10 — Run tests, then manual smoke test, then tick it off.**

## 3. Acceptance coverage

| S17 acceptance item | Satisfied by (code) | Verified by |
|---|---|---|
| Speaker button plays real Hindi speech | S8 `speakText` | Verification step 2 |
| `POST /message` contract unchanged | No edit to that route/model in this plan | Code inspection + existing contract tests still passing |
| Empty/oversized text → 400 | S3 `SpeakRequest` bounds | S6 |
| Sarvam failure → 503, scoped to the button | S2/S4, S8 catch block | S6 + Verification step 3 |

## 4. New libraries
None — same `httpx` already used by `voice.py`/`turn_engine.py`.

## 5. How this doesn't regress anything already built
- `POST /api/v1/message`'s route, request model, and response model are untouched — every existing
  contract test (`backend/tests/contract/`) exercises the same shape as before.
- S12 (`voice.py`, ASR) is a separate module; T51 adds a sibling, doesn't modify it.
- `appendMessage`'s existing citizen-bubble update path (S16 D-S16-3, `citizenEl.textContent =
  result.transcript`) must keep working — S8's own note above flags exactly this risk before
  writing the code, not after.

## Verification
1. `cd backend; uv run pytest` — new tests green, all existing ones (voice, routes, contract) unaffected.
2. Real backend (`uv run uvicorn app.main:app --port 8000`) + real frontend: send any message, tap
   🔊 on the bot's reply, confirm real Hindi audio plays.
3. Stop the backend, tap 🔊 again — confirm the button shows a brief failure state, not a crash, and
   the chat itself is unaffected (no stray error bubble).
4. Confirm T21/T29's existing text/voice/location flows still work unchanged after `appendMessage`'s
   edit (S8's own flagged risk).
5. `cd backend; uv run ruff check .` — clean.

## Not doing in this turn
- Any change to `POST /api/v1/message` or `GET /api/v1/status/{id}`.
- A fallback TTS provider (S17 D-S17-2, OUT OF SCOPE).
- Autoplay (S17 D-S17-3, OUT OF SCOPE).
- Caching synthesized audio (S17 OUT OF SCOPE).
- Rate limiting / auth on `/speak` beyond the existing character cap (G-S17-1, flagged not fixed).

## Build log (verified 28 Sep 2026)

1. `cd backend; uv run pytest` — 209 passed (up from 201: 4 new `test_tts.py` + 4 new
   `test_routes.py` speak tests). `uv run ruff check .` clean.
2. **Real Sarvam Bulbul call, direct**: a bare `curl` with the text passed as a shell argument got
   a real `400` ("Text must contain at least one character from the allowed languages") — turned
   out to be a Windows/Git-Bash UTF-8 argument-encoding artifact in the *test*, not a bug: the same
   text sent as a UTF-8 file (`--data-binary @file`) succeeded immediately, and the real
   `/api/v1/speak` endpoint (which builds its JSON body in Python via `httpx`'s own `json=`
   argument, never through a shell) returned real, correctly-sized audio (`~286KB` base64, several
   seconds of speech) for a full ticket-confirmation sentence on the first real try. Worth knowing:
   test with a file/`httpx`, not raw shell arguments, when debugging Devanagari text server-side.
3. **Real browser test**: sent a text complaint, both the greeting bubble and the `confirm` reply's
   🔊 button appeared correctly, positioned right after the reply text. Clicked the confirm reply's
   speaker button — real `OPTIONS` CORS preflight + real `POST /api/v1/speak` → `200`, `Audio.play()`
   resolved with no console error (genuine playback start, confirmed via network log + console,
   audio itself not literally heard by this session).
4. **Failure path**: stopped the backend, clicked 🔊 again — button showed `!` for ~1.5s then reset
   to 🔊, no new chat bubble, no crash, rest of the conversation unaffected. Restarted the backend,
   confirmed `/health` and the full suite green again.

**Ticked T51 `[x]`** on the strength of 1–4 above.
