# Samadhan

A project developed as part of Skill Development.

## Getting Started

```bash
git clone https://github.com/krishnakantnagina/Samadhan.git
cd Samadhan
```

## Description

_Add a short description of what Samadhan does and the problem it solves._

## Features

- _Feature 1_
- _Feature 2_

## Tech Stack

- _List languages, frameworks and tools here_

## Deployment

See [`docs/DEPLOY.md`](docs/DEPLOY.md) (Railway API, Vercel website, Streamlit dashboard) and spec `docs/specs/S22-deploy.md`. Local run: `docs/ONBOARDING.md`.

## Attribution

Every library, API and template used (hackathon organizer requirement). Keep this list up to date.

Backend (`backend/pyproject.toml`):

- [FastAPI](https://fastapi.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/), [Uvicorn](https://www.uvicorn.org/), [python-multipart](https://github.com/Kludex/python-multipart)
- [httpx](https://www.python-httpx.org/), [PyYAML](https://pyyaml.org/) (service spec loader)
- [Groq API](https://console.groq.com/docs) (Turn Engine LLM, JSON mode, primary), [Google Gemini API](https://ai.google.dev/gemini-api/docs) (Turn Engine LLM fallback) — called via `httpx`, no SDK
- [Supabase](https://supabase.com/) (Postgres + Storage, via [`supabase-py`](https://github.com/supabase/supabase-py)) — session manager
- [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) — fuzzy ward-name matching (jurisdiction resolver)
- [Sarvam AI API](https://docs.sarvam.ai/) (voice-to-text, primary), [Groq Whisper](https://console.groq.com/docs/speech-to-text) (voice-to-text fallback) — called via `httpx`, no SDK, no FFmpeg
- [Sarvam Bulbul TTS API](https://docs.sarvam.ai/api-reference-docs/text-to-speech/api/rest-api) (text-to-speech reply, speaker button) — called via `httpx`, no SDK, no fallback provider
- Hosting: [Railway](https://railway.com/) (API, Docker), [Vercel](https://vercel.com/) (static website), [Streamlit Community Cloud](https://streamlit.io/cloud) (dashboard)
- Container base image: [`ghcr.io/astral-sh/uv`](https://github.com/astral-sh/uv)
- Dev tools: [pytest](https://pytest.org/), [Ruff](https://docs.astral.sh/ruff/), [uv](https://docs.astral.sh/uv/)

## Author

Krishnakant Nagina
