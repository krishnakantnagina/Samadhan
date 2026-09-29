# Samadhan

A project developed as part of Skill Development.

## Getting Started

```bash
git clone https://github.com/krishnakantnagina/Samadhan.git
cd Samadhan
```

## Description

Samadhan is a voice-first chatbot for citizen grievances in Madhya Pradesh. A citizen speaks or types a complaint in
Hindi, Hinglish or a local dialect. The bot works out what kind of message it is (a complaint, a question about a
government document, or something unrelated), picks the right **department**, asks only for what is missing, and after
confirmation creates a ticket (`SMD-xxxx`) at the right **office**. The citizen can check status by complaint ID; officers
manage tickets, corrections and a map on a dashboard. The idea is to understand a complaint well enough to route it, not to
transcribe a dialect perfectly.

Built for the MPOnline Idea & Innovation Hackathon 2026, Problem Statement 5. Pilot: Bhopal. Departments: water supply, plus
DEMO electricity, roads, sanitation and a general triage desk (all office data for the extra departments is labelled DEMO).

## Features

- _Feature 1_
- _Feature 2_

## Tech Stack

- _List languages, frameworks and tools here_

## Deployment

See [`docs/DEPLOY.md`](docs/DEPLOY.md) (Railway API, Vercel website, Streamlit dashboard) or [`docs/DEPLOY_RENDER.md`](docs/DEPLOY_RENDER.md) (everything on Render), and spec `docs/specs/S22-deploy.md`. Local run: `docs/ONBOARDING.md`.

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
- Hosting: [Railway](https://railway.com/) (API, Docker), [Vercel](https://vercel.com/) (static website), [Streamlit Community Cloud](https://streamlit.io/cloud) (dashboard), or [Render](https://render.com/) for all three
- Container base image: [`ghcr.io/astral-sh/uv`](https://github.com/astral-sh/uv)
- Dev tools: [pytest](https://pytest.org/), [Ruff](https://docs.astral.sh/ruff/), [uv](https://docs.astral.sh/uv/)

## Author

Krishnakant Nagina
