# Plan: T26 — Voice (upload → Sarvam/Groq Whisper → storage)

Ticket: `docs/TICKETS.md` T26 (owner Dev, depends on T18 — `[x]`, done when "Voice flow works").
Spec: `docs/specs/S12-voice.md`. No FFmpeg (D-S12-1, verified against both providers' current APIs).

## Files

| Path | Action |
|---|---|
| `backend/app/config.py` | Edit — add `get_voice_config()` (`SARVAM_API_KEY`, `SARVAM_MODEL`, `GROQ_WHISPER_MODEL`) |
| `backend/app/voice.py` | Create — `transcribe()`, `VoiceUnavailable`, `VoiceResult` |
| `backend/app/routes.py` | Edit — replace the blanket audio `503` with a real call to `voice.transcribe`, wire `transcript` into the Turn Engine call and `action=error` for an empty transcript |
| `backend/tests/test_voice.py` | Create — fake HTTP + storage, mirrors T12's fake-provider pattern |
| `backend/tests/test_routes.py` | Edit — replace `test_audio_rejected_as_service_unavailable` with real audio-flow tests |
| `.env.example` | Edit — add `SARVAM_MODEL`, `GROQ_WHISPER_MODEL` |
| `README.md` | Edit — Attribution: Sarvam API |
| `docs/TICKETS.md` | Tick T26 |

## `app/voice.py` sketch
```python
EXT_BY_CONTENT_TYPE = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/wav": "wav"}
PROVIDER_TIMEOUT_SECONDS = 8.0  # PROJECT.md section 7, S04 section 5


class VoiceUnavailable(RuntimeError): ...


@dataclass(frozen=True)
class VoiceResult:
    transcript: str
    audio_path: str


def _upload(audio_bytes, content_type, session_id, message_id, *, client) -> str:
    ext = EXT_BY_CONTENT_TYPE[content_type]
    path = f"{session_id}/{message_id}.{ext}"
    client.storage.from_("audio").upload(path, audio_bytes, file_options={"content-type": content_type})
    return path


def _sarvam(audio_bytes, content_type, config) -> str:
    r = httpx.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": config.sarvam_api_key},
        files={"file": ("audio", audio_bytes, content_type)},
        data={"model": config.sarvam_model, "language_code": "unknown", "mode": "transcribe"},
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    r.raise_for_status()
    return r.json()["transcript"]


def _groq_whisper(audio_bytes, content_type, config) -> str:
    r = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {config.groq_api_key}"},
        files={"file": ("audio", audio_bytes, content_type)},
        data={"model": config.groq_whisper_model},
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )
    r.raise_for_status()
    return r.json()["text"]


def transcribe(
    audio_bytes: bytes, content_type: str, session_id: uuid.UUID, message_id: uuid.UUID,
    *, client: Client | None = None,
) -> VoiceResult:
    client = client or get_client()
    audio_path = _upload(audio_bytes, content_type, session_id, message_id, client=client)  # D-S12-3

    config = get_voice_config()
    for attempt in (_sarvam, _groq_whisper):
        try:
            transcript = attempt(audio_bytes, content_type, config)
            return VoiceResult(transcript=transcript, audio_path=audio_path)
        except httpx.HTTPError:
            continue
    raise VoiceUnavailable("both ASR providers failed")
```
Same injectable-seam idea as T12/T14, but here the seam is `client` (storage) — the two HTTP calls
are tested via `httpx`-mocking (respx-style monkeypatch on `httpx.post`, no new dependency) since
unlike S05 there's only one real call shape per provider, not enough surface to justify a `Provider`
protocol.

## `routes.py` change
Replace:
```python
raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, "Voice input is not available yet.")
```
with:
```python
try:
    voice_result = voice.transcribe(await audio.read(), api.normalise_content_type(audio.content_type), session_id, message_id)
except voice.VoiceUnavailable as exc:
    raise ApiError(api.ErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc
transcript = voice_result.transcript
audio_path = voice_result.audio_path
```
then fall through to steps 2–9 using `text = text or (transcript or None)` for the Turn Engine call,
and short-circuit to `action=error` (S01 D-A6) with a citizen-safe reply when `transcript` is empty —
new branch, since T18 never needed it for text-only turns. **This reintroduces `await` for
`audio.read()`**, so the route goes back to `async def` for the audio path — or, simpler and
consistent with D-S04-3's sync-everywhere reasoning, use `audio.file.read()` (sync, blocking, exactly
what FastAPI's own `UploadFile` docs recommend for `def` routes) so the whole route stays sync. Use
`audio.file.read()`.

`audio_path` is threaded into `session.save_turn`'s `audio_path` param (previously always `None`).

## Tests (`test_voice.py`)
- `test_uploads_before_transcribing` — call order via monkeypatched `httpx.post` + fake storage.
- `test_sarvam_success_skips_groq`.
- `test_sarvam_failure_falls_back_to_groq`.
- `test_both_fail_raises_voice_unavailable`.
- `test_empty_transcript_is_not_an_error` — returns `VoiceResult(transcript="", ...)`, doesn't raise.
- `test_extension_mapping_for_each_accepted_content_type`.

## Tests (`test_routes.py`, replacing the old audio-503 test)
- `test_audio_transcribed_and_fed_to_turn_engine` — monkeypatch `voice.transcribe` to return a
  canned transcript, assert `turn_engine.run_turn` receives it as `text`.
- `test_empty_transcript_returns_action_error`.
- `test_voice_unavailable_is_503`.
- Keep `test_unsupported_audio_type_is_415` / `test_oversized_audio_is_413` unchanged — still run
  before `voice.transcribe` is ever called.

## Verification
1. `uv run pytest` + `ruff check`/`format`.
2. Manual, real `.env`: record or reuse a short `.webm`/`.wav` sample, POST it through
   `TestClient(app.main.app)`, confirm a real transcript comes back and a row appears in the `audio`
   Storage bucket.
