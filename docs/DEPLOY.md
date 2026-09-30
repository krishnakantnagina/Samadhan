# Deploy checklist (T32, spec S22)

Order matters: **API first** (you need its URL), then website, then dashboard. Accounts and secrets are yours
to create and paste; nothing here needs a secret committed to git. Env-var names are in `.env.example`.

## 1. API on Railway
1. Railway → New Project → Deploy from GitHub repo → this repo. **Keep the root directory at the repo root**
   (the API needs `specs/`, see S22 D-S22-1). Railway finds the `Dockerfile` by itself.
2. Settings → Variables: add every API var listed in `docs/specs/S22-deploy.md` §4. Leave `ALLOWED_ORIGINS`
   as a placeholder for now, you set it in step 2.
3. Settings → Networking → Generate Domain. Note the URL, e.g. `https://xxxx.up.railway.app`.
4. Check: open `<railway-url>/health` → `{"status":"ok"}`, and `<railway-url>/docs`.

## 2. Website on Vercel
1. Vercel → Add New Project → same repo. Framework preset **Other**. Vercel reads `vercel.json`
   (build command writes `frontend/config.js`; output directory `frontend`).
2. Environment Variable: `SAMADHAN_API_BASE` = the Railway URL, no trailing slash. The build fails on purpose if it is missing.
3. Deploy. Note the URL, e.g. `https://samadhan.vercel.app`.
4. **Back on Railway**: set `ALLOWED_ORIGINS` = that exact Vercel origin (scheme + host, no path, no trailing slash;
   comma-separate to add more, e.g. a custom domain). Redeploy. A mismatch shows as "server unreachable" in the chat.

## 3. Dashboard on Streamlit Community Cloud
1. share.streamlit.io → New app → this repo, branch `main`, main file `dashboard/src/dashboard/app.py`.
2. Advanced settings → Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DASHBOARD_PASSWORD`.
3. Dependencies come from `dashboard/pyproject.toml` / `uv.lock`. If the build can't find them, point the
   "dependencies file" at `dashboard/pyproject.toml`.

## 4. Verify (S22 ACCEPTANCE, second list)
- [ ] `<railway>/health` is 200 over HTTPS
- [ ] Vercel site: send a text message, get a reply (CORS ok); status page works with a real `SMD-` id
- [ ] Mic recording and location button work on the HTTPS site (they only work on HTTPS)
- [ ] Voice reply plays
- [ ] Dashboard login works and shows the tickets the site just created
- [ ] Local run still works from a fresh clone (see README / `docs/ONBOARDING.md`)

## 5. Before demo day
- Warm everything up: free tiers sleep, the first request after idle is slow.
- Re-check `GROQ_MODEL` / `GEMINI_MODEL` are still live (`.env.example` notes).
- Supabase free tier pauses after 7 idle days (G-T06-1): open the project once before the freeze.
- Open endpoints: `/message` and `/speak` have no rate limit (G-S17-1). Don't share the API URL publicly.
