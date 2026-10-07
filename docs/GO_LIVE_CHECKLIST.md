# Go-live checklist (Render), written 2026-10-07

For putting the post-submission work (49 departments, district routing, scheme answers, audit fixes, Sarvam speech) on the live site. Read with `docs/DEPLOY_RENDER.md` (how the three
services are set up) and `docs/specs/S38-audit-fixes.md` (what changed). **Nothing here has been run on the live site.** Tests passed locally: backend 880, dashboard 173, frontend 33.

> The hackathon handbook says changes after submission are real (`reference_hackathon-handbook`). Check that deploying is allowed before you push to `main`.

## 1. Before anything: the code
- [ ] The work is on branch `post-submission`; most of it is still uncommitted. Commit it in one go (several tracked files import the new modules).
- [ ] `main` is what Render builds. Merge `post-submission` into `main` only when you decide to go live (pushing `main` redeploys the three services).

## 2. Database (Supabase SQL editor), in this order, once
Already on the live database: `002`, `003`. **Still to run:**
| # | File | Why it must run | If you skip it |
|---|---|---|---|
| 1 | `database/migrations/004_all_department_offices.sql` | Offices (DEMO) for the 45 new departments. | Complaints for those departments go to the Human Evaluation desk for review (they are not lost), so nothing works as designed for them. |
| 2 | `database/migrations/005_district_offices.sql` | `offices.district`, one desk per district per department. Existing rows become `Bhopal`. | Every complaint still goes to the one desk (as today). |
| 3 | `database/migrations/006_ticket_events.sql` | Audit trail of dashboard actions. | The dashboards skip the audit write (a warning in the log). |

Real district desks (names, officers) come from the departments; add them as rows with `district` set (see the comment at the end of 005). The 54 invented desks in
`database/seed_demo_district_offices.sql` are for the local test database only: do **not** run that file on the live database.

## 3. Backend service (`samadhan-kx8b`) environment
Keep what is set today. **Add or check:**
| Name | Value | Why |
|---|---|---|
| `SARVAM_API_KEY` | the new key | speech to text and text to speech |
| `SARVAM_TTS_MODEL` / `SARVAM_TTS_SPEAKER` | `bulbul:v3` / `shubh` (or your choice) | Hindi voice |
| `TTS_CACHE_SIZE` | `300` | bot questions repeat; a repeat costs no speech credit |
| `TRUST_FORWARDED_FOR` | `1` | Render is a proxy: the rate limits must see the visitor's address, not Render's |
| `ALLOWED_ORIGINS` | the website's exact address | unchanged |
| `AUTH_PROVIDER=demo`, `AUTH_REQUIRED=1`, `AUTH_DEMO_IN_PRODUCTION=1` | as today | **the demo PIN lets anyone log in as any number**; real OTP is still to build |
| `INTAKE_V2`, `TYPESAFE_API_KEY` | as today | department routing by Jev |
Leave these **off** for the first go-live (they need free-tier quota that will not last): `SCHEME_LOOKUP`, `SCHEME_EXPLAIN`, `TRIAGE`, `UNDERSTAND_FIRST`, `ASR_PIPELINE`. Turn them on one at a time.
Set the Render **Health Check Path** to `/health/ready` (it checks the database; `/health` only checks the process). API docs are hidden on Render on purpose (`ENABLE_API_DOCS=1` brings them back).

## 4. Dashboard service (`samadhan-dashboard`)
- [ ] Redeploy so it installs the new `pyyaml` (the build command exports from `dashboard/uv.lock`, which is already updated).
- [ ] Keep `DASHBOARD_PASSWORD` strong: five wrong tries now lock the username for 10 minutes.
- [ ] After migration 006, status changes and phone views appear under "Activity on this ticket".

## 5. Website service
Nothing new to set. It now has `privacy.html` (a DRAFT notice: the retention period and the contact line are placeholders to fill in before real citizens use it).

## 6. After deploying: smoke tests (replace the address)
```
curl https://samadhan-kx8b.onrender.com/health/ready                         # {"status":"ok","database":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" https://samadhan-kx8b.onrender.com/docs   # 404 (hidden on purpose)
curl -s -X POST https://samadhan-kx8b.onrender.com/api/v1/speak -H "Content-Type: application/json" -d '{"text":"नमस्ते"}' | head -c 80   # audio_base64 ...
```
- [ ] On a phone: open the website, speak a complaint in Hindi, hear the reply (a reply to your voice plays by itself; a typed reply plays when you tap the speaker).
- [ ] Give a district (for example "राजगढ़ जिला") and check the ticket in the dashboard: once real desks exist for that district it lands there; until then it is marked "needs review".
- [ ] File the same complaint twice quickly: one ticket.
- [ ] Watch the Render logs for the first day: `audit event not recorded`, `offices.district is missing`, `no office for department` all mean a migration or office data is missing.

## 7. Rolling back
- Code: redeploy the previous commit in Render. The migrations are additive, so the old code keeps working with them applied.
- Migration 005 only if you must: `DROP INDEX offices_one_active_district_office; CREATE UNIQUE INDEX offices_one_active_district_per_department ON offices (department) WHERE level = 'district' AND active;` (works only while each department still has ONE active district desk).

## 8. Known gaps (not blockers for a pilot, blockers for real public use)
Real OTP login; privacy retention period and contact address; the status lookup is open to anyone with a ticket number; dashboard role separation is in the screen only; the Dockerfile and CI file were
never run on a real host; Gemini free-tier limits (scheme answers) and Sarvam credit need a paid plan for real traffic.
