# T09 — Voice samples (3 of 3)

Real human-spoken Hindi audio, recovered from the project's live Supabase `audio` storage bucket
(citizen-simulation recordings made during T29/T52 manual testing on 28 Sep 2026, real
Sarvam/Groq Whisper transcription — not synthetic/AI-generated audio). This is not a fresh
purpose-recording; it's real speech that was already sitting in the project's own storage from
earlier live testing, reused here because it already exists and is genuinely intelligible speech
(unlike the project's only other real-audio test, which was silence/tone and produced empty
transcripts — see `docs/plans/T29-plan.md`'s build log).

| File | Real transcript (Sarvam/Groq Whisper, live) | Size |
|---|---|---|
| `sample1_issue.webm` | हाय, मुझे दिक्कत है कि मेरे नाप पे पानी नहीं आ रहा है। | 138,120 bytes |
| `sample2_issue_detail.webm` | मेरे यहां पे पानी नहीं आ रहा है मतलब मेरे यहां का नल खराब है। | 169,998 bytes |
| `sample3_location.webm` | मैं मिश्रा से हूँ। मेरे गाँव का नाम जाटखेड़ी है। ये वार्ड नंबर 29 में आता है शायद। | 264,666 bytes |

All three are `audio/webm` (Chrome's default `MediaRecorder` output), the same format the real
pipeline already accepts natively (S12 D-S12-1, no FFmpeg). Each was already proven, live, to
produce a correct real transcript and a correct Turn Engine response — the full conversation this
came from (session `3687e879-...`) proceeded through location → confirm → a real submitted ticket,
`SMD-0019` (see `docs/specs/S18-citizen-ui-redesign.md` G-S18-3, `docs/plans/T29-plan.md`).

## What T09 still needs

T09's own done-when is "15 test sentences + 3 voice samples — Shared." This closes the voice-sample
half. The **15 text test sentences** (for T13's prompt-accuracy pass, ≥13/15) are still not
written — that's a content-authoring task, separate from anything requiring a microphone, and
still open.
