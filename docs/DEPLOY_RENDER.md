# Deploy on Render (alternative to Railway + Vercel), T32, spec S22

Render can host all three parts on free `*.onrender.com` addresses with HTTPS. Same order as `docs/DEPLOY.md`: **backend first**
(you need its URL), then the website, then tell the backend which website may call it, then (optionally) the dashboard.
Account creation and pasting secrets are yours to do; nothing here needs a secret in git. Env-var names are in `.env.example`.

> Written from Render's documented behaviour and this repo's files, **not tested on a real Render account** (and the Docker image has
> never been built on any host). Button and field names may differ slightly. If a build fails, send me the log.

Why HTTPS matters: phone browsers only allow the **microphone and GPS on HTTPS pages**. Render gives HTTPS automatically, which is
what makes the real-Android test (T52 box "b") possible without your laptop.

## 0. Before you start
- The repo is on GitHub (`https://github.com/krishnakantnagina/Samadhan`), branch `main`.
- Have ready the values from your local `.env`: `SARVAM_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `SUPABASE_URL`,
  `SUPABASE_SERVICE_KEY`, `DASHBOARD_PASSWORD` and the model names.
- Rotate the Groq key you pasted into chat earlier, and use the new one.

## 1. Backend: Web Service (Docker)
1. Render dashboard → **New +** → **Web Service** → connect the GitHub repo.
2. Settings:
   | Field | Value |
   |---|---|
   | Name | `samadhan-api` (any name; it becomes the URL) |
   | Branch | `main` |
   | Runtime / Language | **Docker** |
   | Root Directory | **leave empty** (the API needs `specs/` at the repo root, S22 D-S22-1) |
   | Dockerfile Path | `./Dockerfile` (the default) |
   | Instance Type | Free |
   | Health Check Path | `/health` |
3. **Environment** → add these (names exactly):
   `SARVAM_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `LLM_PROVIDER` (`groq`),
   `GROQ_MODEL`, `GEMINI_MODEL`, `SARVAM_MODEL`, `SARVAM_TTS_MODEL`, `SARVAM_TTS_SPEAKER`, `GROQ_WHISPER_MODEL`
   (values as in `.env.example`; optional: `GROQ_FALLBACK_MODELS`, `GROQ_REASONING_EFFORT`), and a **placeholder**
   `ALLOWED_ORIGINS` = `http://localhost:5500` (you change it in step 3). Do not set `PORT`: Render sets it and the Dockerfile reads it.
4. **Create Web Service.** The first build takes several minutes. When it says Live, note the URL, e.g.
   `https://samadhan-api.onrender.com`.
5. Check: open `<backend-url>/health` → `{"status":"ok"}` and `<backend-url>/docs`.

## 2. Website: Static Site
1. **New +** → **Static Site** → same repo.
2. Settings:
   | Field | Value |
   |---|---|
   | Name | `samadhan` (becomes the URL) |
   | Branch | `main` |
   | Root Directory | leave empty |
   | Build Command | the one-line command in the box just below (copy it exactly: no backslashes) |
   | Publish Directory | `frontend` |
   **Build Command** (copy exactly; the two `|` characters are plain, no backslashes):
   ```
   test -n "$SAMADHAN_API_BASE" || { echo "SAMADHAN_API_BASE is not set" >&2; exit 1; }; printf "window.SAMADHAN_API_BASE = '%s';\n" "$SAMADHAN_API_BASE" > frontend/config.js
   ```
   (The build command is the same one `vercel.json` uses: it writes the backend address into `frontend/config.js`. It fails on
   purpose if the variable is missing.)
3. **Environment** → `SAMADHAN_API_BASE` = the backend URL from step 1, **no trailing slash**.
4. **Create Static Site.** Note its URL, e.g. `https://samadhan.onrender.com`.

## 3. Tell the backend which website may call it (CORS)
1. Backend service → **Environment** → set `ALLOWED_ORIGINS` = the website's exact origin: `https://samadhan.onrender.com`
   (scheme + host, no path, no trailing slash; comma-separate to add more, e.g. a second address).
2. Save. Render restarts the service. A mismatch shows as **"server unreachable"** in the chat.

## 4. Dashboard (optional here; Streamlit Community Cloud in `docs/DEPLOY.md` §3 is simpler)
If you want it on Render too: **New +** → **Web Service**, runtime **Python**, Root Directory empty.
| Field | Value |
|---|---|
| Build Command | `pip install uv && cd dashboard && uv sync --frozen --no-dev` |
| Start Command | `cd dashboard && uv run streamlit run src/dashboard/app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true` |
Environment: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DASHBOARD_PASSWORD`, and `PYTHON_VERSION` = `3.12` (the project needs 3.12+).
The dashboard is password-gated (S13). Keep the URL private.

## 5. Verify (S22 ACCEPTANCE, second list)
- [ ] `<backend>/health` is 200 over HTTPS
- [ ] Website: send a text message and get a reply; open the status page with a real `SMD-` id
- [ ] Mic recording, the speaker/voice note, and the location button work (HTTPS is what allows them)
- [ ] Dashboard login works and shows the tickets the site just created
- [ ] **Phone test (T52 box "b"):** on the Android phone, mobile data, open the website URL: type a complaint, hold the mic and speak
      one, allow location. Note anything odd.
- [ ] The local run still works from a fresh clone (README / `docs/ONBOARDING.md`), as the backup

## 6. Free-tier behaviour you must plan for
- As far as I know, free Render web services **sleep after ~15 minutes without traffic**, and the next request takes roughly
  30-60 seconds to wake them. **Open the site and send one message 5 minutes before the demo**, and again if you pause for a while.
  Static sites do not sleep. (Free instance hours are limited per month; check your account's numbers.)
- **Groq free tier:** 8,000 tokens per minute per model (see `docs/specs/S28`, capacity finding). Don't click quickly during the demo.
- Supabase free projects pause after 7 idle days (G-T06-1): open the project once before the freeze.
- The free tiers can change; check Render's pricing page on the day.

## 7. Troubleshooting
| Symptom | Likely cause and fix |
|---|---|
| Chat says **"server unreachable"** | `ALLOWED_ORIGINS` does not match the website's exact origin, or `SAMADHAN_API_BASE` is wrong/has a trailing slash, or the backend is asleep (wait a minute and retry). |
| Static Site build fails with `SAMADHAN_API_BASE is not set` | Add the env var on the Static Site (not the backend) and redeploy. |
| First message after a pause takes ~1 minute | Cold start (free tier). Warm it up beforehand. |
| Reply says a temporary problem / 503 | The LLM quota is used up; wait a minute (S26 tries three Groq models and Gemini). |
| Mic or location button does nothing on the phone | The page is not on HTTPS, or the browser permission was denied for the site. |
| Docker build fails | Send me the build log; the image was never built anywhere before. |
| Dashboard build fails on `uv` | Use Streamlit Community Cloud instead (`docs/DEPLOY.md` §3). |

## 8. Safety notes
- Keys live only in Render's Environment tab, never in git.
- `/message` and `/speak` have no rate limit or login (G-S17-1). Don't post the API URL publicly.
- After the 30 Sep submission nothing in the project changes until the event ends (organizer rule). Finish and test the deploy first.
- Rollback: Render keeps previous deploys; use its deploy history to go back, or fall back to the local run.
