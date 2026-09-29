# S22 — Deployment (Railway API, Vercel website, Streamlit dashboard)
Implements: T32 · Depends on: S04 (`SPECS_DIR`, D-S04-1), S13 (dashboard env), PROJECT.md §6/§8 · Version: v1 · Status: Draft

## 1. What T32 covers
"Deploy + local laptop run verified", done when **URLs + local both work**. This spec + `docs/DEPLOY.md`
prepare everything that can be prepared in the repo. The account steps (creating Railway/Vercel/Streamlit
projects, pasting secrets) are the Lead's: an assistant must not create accounts or enter keys.

## 2. Targets
| Piece | Host | Root / entry | Public? |
|---|---|---|---|
| API | Railway | repo root, `Dockerfile` | yes (HTTPS) |
| Website | Vercel, static | `frontend/` served, `config.js` generated at build | yes (HTTPS) |
| Dashboard | Streamlit Community Cloud | `dashboard/src/dashboard/app.py` | yes, password-gated (S13) |
| DB | Supabase (already live) | unchanged | no |

## 3. Decisions
| # | Decision | Reason |
|---|---|---|
| D-S22-1 | Railway builds from the **repo root** with a `Dockerfile`, not from `backend/` | `main.py` finds specs at `<repo>/specs` (D-S04-1, `parents[2]`); a `backend/`-rooted deploy would not contain `specs/`. Changing that path is a contract change, deploying from the root is not |
| D-S22-2 | `API_BASE` comes from `frontend/config.js` (`window.SAMADHAN_API_BASE`), default `http://localhost:8000` | No build step exists in `frontend/` (PROJECT.md §9), so the URL can't be injected by a bundler. Committed default keeps the local run unchanged; Vercel's `buildCommand` overwrites the file from the env var `SAMADHAN_API_BASE` |
| D-S22-3 | `.dockerignore` excludes `.env`, `.venv`, `submission/`, tests data | Secrets must never enter an image (CLAUDE.md rule) |
| D-S22-4 | Secrets live only in each host's env settings; the dashboard reads them as env vars (Streamlit exposes secrets as env vars) | S13/PROJECT.md §8 |

## 4. Env vars per host
- **Railway (API):** `SARVAM_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
  `LLM_PROVIDER`, `GROQ_MODEL`, `GEMINI_MODEL`, `SARVAM_MODEL`, `SARVAM_TTS_MODEL`, `SARVAM_TTS_SPEAKER`,
  `GROQ_WHISPER_MODEL`, `ALLOWED_ORIGINS` = the exact Vercel origin (no trailing slash). `PORT` is set by Railway.
- **Vercel (website):** `SAMADHAN_API_BASE` = the Railway public URL (no trailing slash).
- **Streamlit (dashboard):** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DASHBOARD_PASSWORD`.
`SUPABASE_ANON_KEY` and `SUPABASE_DB_URL` are not needed at runtime.

## 5. Known risks (from GAPS.md, not solved here)
- G-S17-1: `/speak` and `/message` are unauthenticated and un-rate-limited on a public URL.
- G-T06-1: Supabase free tier pauses after 7 idle days, inside the freeze window.
- Railway/Streamlit free tiers may sleep; first request after idle is slow. Warm it before the demo.
- Model ids drift (`.env.example` comments): re-check `GROQ_MODEL` / `GEMINI_MODEL` right before demo day.

## ACCEPTANCE
**Prepared in the repo (verifiable here):**
- [ ] `frontend/config.js` + script tags; all three JS files read it; local run unchanged
- [ ] `Dockerfile` + `.dockerignore`; the container start command works from the repo root locally (`/health`)
- [ ] `vercel.json` build command generates a correct `config.js`
- [ ] `docs/DEPLOY.md` step-by-step; README links it
- [ ] pytest + ruff still pass; no secret in any committed file

**Done by the Lead (cannot be verified from the repo):**
- [ ] Railway `/health` returns 200 over HTTPS
- [ ] Vercel site loads, chat round trip works against Railway (CORS ok)
- [ ] Mic + GPS work on the HTTPS site
- [ ] Dashboard loads on Streamlit Cloud, login works, sees real tickets
- [ ] Local laptop run still works (fresh clone, README steps)
