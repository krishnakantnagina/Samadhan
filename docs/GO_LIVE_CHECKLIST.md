# Go-live checklist (Render), written 2026-10-07, state re-checked 2026-10-10

For putting the post-submission work (49 departments, district routing, scheme answers, audit fixes, Sarvam speech) on the live site. Read with `docs/DEPLOY_RENDER.md` (how the three
services are set up) and `docs/specs/S38-audit-fixes.md` (what changed).

**State on 2026-10-10 (read-only probe of the live Supabase database, see section 2):** every migration up to `008` **is already applied**. What is still outstanding is the *code*
(uncommitted, not merged to `main`, so nothing in it is deployed) and the *desk logins* (`dashboard_accounts` is empty). The earlier note here saying "nothing has been run on the
live site" was out of date and has been corrected.

Tests passing locally on 2026-10-10: **backend 907 passed / 1 skipped, dashboard 206, frontend 38**. Both dashboards also render with zero exceptions
(`streamlit.testing.v1.AppTest` on `cm_app.py` and `app.py`).

> The hackathon handbook says changes after submission are real (`reference_hackathon-handbook`). Check that deploying is allowed before you push to `main`.

## 1. Before anything: the code  ← **this is now the real blocker**
- [ ] The work is on branch `post-submission`; most of it is still uncommitted (22 changed/untracked paths on 2026-10-10). Commit it in one go (several tracked files import the new modules).
      Untracked modules that tracked files now need: `dashboard/src/dashboard/cm/charts.py` (imported by `cm/pages.py` **and** `app.py`), `dashboard/src/dashboard/cm/make_desk_accounts.py`,
      `dashboard/src/dashboard/local_app.py`, `dashboard/src/dashboard/local_client.py`. Committing the modified files **without** `charts.py` would break both dashboards on the server.
- [ ] `main` is what Render builds. Merge `post-submission` into `main` only when you decide to go live (pushing `main` redeploys the three services).
- [ ] Nothing in the post-submission work is deployed yet: the live site still runs the pre-submission code, even though the database is already migrated past it.

## 2. Database (Supabase SQL editor) — ALL APPLIED, nothing left to run

`002`–`008` are **all on the live database**. Verified 2026-10-10 by a read-only probe (counts below); re-running any of them is safe but unnecessary.

| # | File | Status | Evidence on the live database |
|---|---|---|---|
| 1 | `004_all_department_offices.sql` | **applied** | the new departments have offices (e.g. `AYUSH Department` = 60 offices) |
| 2 | `005_district_offices.sql` | **applied** | `offices.district` column present and readable |
| 3 | `006_ticket_events.sql` | **applied** | `ticket_events` table exists, 13 rows |
| 4 | `007_district_desks.sql` | **applied** | **2,103 district desks + 11 state desks** |
| 5 | `008_dashboard_accounts.sql` | **applied (but empty)** | `dashboard_accounts` table exists, **0 rows** — no desk login has been issued yet |

Live totals on 2026-10-10: **2,359 offices** (2,103 district + 11 state + 245 ward), **59 tickets**.

> The one thing still to do here is **not a migration**: `dashboard_accounts` is empty, so on the live dashboard only `admin` + `DASHBOARD_PASSWORD` can log in. See section 4.

The desks in 007 are **designations without officers** (for example "Chief Medical and Health Officer (CMHO), Rajgarh"), taken from the official district portals; see `docs/DISTRICT_DESKS.md`
for the source and the confidence of each. Send each department its line to confirm, and add the officer and contact when it replies. Re-running 007 is safe.

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
- [ ] **Issue the desk logins — none exist yet.** Migration 008 is applied but `dashboard_accounts` has **0 rows**, so today only `admin` + `DASHBOARD_PASSWORD` can sign in to the live
      dashboard. Log in as `admin`, open **Accounts and Roles** → **Desk access**, choose a department and a desk, and give the officer a login. The temporary password is shown once; the
      officer must choose their own at the first login. When an officer is transferred use **Hand over this desk** (design: `docs/specs/S40-desk-access.md`).
- [ ] Redeploy so it installs the new `pyyaml` (the build command exports from `dashboard/uv.lock`, which is already updated).
- [ ] Keep `DASHBOARD_PASSWORD` strong: five wrong tries now lock the username for 10 minutes.
- [x] Migration 006 is applied, so status changes and phone views already appear under "Activity on this ticket".

> **Do not rely on `local-research/demo_accounts.json` for the live site.** That file (the demo logins, plus the 2,101 generated desk logins in `local-research/DESK_ACCOUNTS.md`) is
> **git-excluded**, so it is never deployed. It is for local work only. Live desk logins must come from the **Desk access** screen, which writes to `dashboard_accounts`.
> `DESK_ACCOUNTS.md` holds those 2,101 passwords in plain text: delete it once the real logins are issued, and never commit or paste it.

## 5. Website service
Nothing new to set. It now has `privacy.html` (a DRAFT notice: the retention period and the contact line are placeholders to fill in before real citizens use it).

## 6. After deploying: smoke tests (replace the address)
```
curl https://samadhan-kx8b.onrender.com/health/ready                         # {"status":"ok","database":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" https://samadhan-kx8b.onrender.com/docs   # 404 (hidden on purpose)
curl -s -X POST https://samadhan-kx8b.onrender.com/api/v1/speak -H "Content-Type: application/json" -d '{"text":"नमस्ते"}' | head -c 80   # audio_base64 ...
```
- [ ] On a phone: open the website, speak a complaint in Hindi, hear the reply (a reply to your voice plays by itself; a typed reply plays when you tap the speaker).
- [ ] Give a district (for example "राजगढ़ जिला") and check the ticket in the dashboard: the real desks for all 55 districts **are** on the database (007 applied), so it should land on that
      district's desk, not on "needs review". A "needs review" here means the department could not be decided, not a missing desk.
- [ ] File the same complaint twice quickly: one ticket.
- [ ] Watch the Render logs for the first day: `audit event not recorded`, `offices.district is missing`, `no office for department` all mean a migration or office data is missing — none of
      these should appear now that 004–008 are applied, so treat any of them as a real regression.

## 7. Rolling back
- Code: redeploy the previous commit in Render. The migrations are additive, so the old code keeps working with them applied.
- Migration 005 only if you must: `DROP INDEX offices_one_active_district_office; CREATE UNIQUE INDEX offices_one_active_district_per_department ON offices (department) WHERE level = 'district' AND active;` (works only while each department still has ONE active district desk).

## 8. Known gaps (not blockers for a pilot, blockers for real public use)
Real OTP login; privacy retention period and contact address; the status lookup is open to anyone with a ticket number; dashboard role separation is in the screen only; the Dockerfile and CI file were
never run on a real host; Gemini free-tier limits (scheme answers) and Sarvam credit need a paid plan for real traffic.
