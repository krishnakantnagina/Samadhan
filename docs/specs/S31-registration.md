# S31 — Registration, saved login, structured location, Human Evaluation (BUILT behind switches, 2026-10-01)

Status: **implemented; registration OFF by default** (`AUTH_PROVIDER`, `AUTH_REQUIRED`). Decisions by the Lead, 2026-10-01. Code: `backend/app/auth.py`, `auth_routes.py`,
`location_details.py`, `ticketing.py`, `frontend/auth.js`, `database/migrations/002_registration_and_location.sql`. Tests: `backend/tests/test_auth.py` (40),
`test_location_details.py` (32), `test_ticketing_s31.py` (6), `frontend/tests/auth.test.mjs` (9), `dashboard/tests/test_tickets_s31.py` (3).

## 1. Decisions
- **Filing a complaint requires registration** (phone). **General enquiries and status checks do not.** Applying for a service (e.g. income certificate) will also need
  registration later; in the hackathon demo the bot only gives the official link and guidance, so no registration is asked.
- **Phone is the identity; it is stored permanently** (demo). Aadhaar-based registration is a **plan for when the government approves**; until then phone only. The Aadhaar
  number must never be stored (UIDAI: only authorised entities, in a separate vault, by reference key): a future provider would store a reference key.
- **Why the phone:** the officer handling the complaint **calls the citizen back** on it. The dashboard shows it (with a call link) in the opened ticket only.
- **General Triage is removed.** Complaints the AI cannot place go to a **Human Evaluation** queue (S30), a queue not a department.

## 2. Flow
Jev department -> (one question if unsure) -> spec questions -> location -> **district / tehsil / nearest place (once; "पता नहीं" accepted)** -> duration ->
read-back and confirm -> **login (if not logged in): the confirmed draft is kept** -> ticket created and linked to the user -> complaint id.
Server rule: a confirmed complaint with no valid login returns `action=ask`, `ask_for="login"`, `awaiting_confirmation=true` (draft kept). The website shows the login screen,
then re-sends the confirmation. A closed login screen keeps the draft; typing yes later asks again.

## 3. Identity layer (the swap points)
- `IdentityProvider` (`start`, `verify`). `DemoProvider`: any 10-digit phone, fixed PIN **5555**, hint "Demo: enter PIN 5555". A real SMS OTP provider is one class registered in
  `PROVIDERS` and `AUTH_PROVIDER=<name>`; the website, endpoints and storage do not change. WhatsApp / call identities use `AuthService.user_for_channel(phone, "whatsapp")`: same
  user table, no PIN, no token.
- Safety: the demo provider only runs when `AUTH_PROVIDER=demo` and **refuses on a production host** (`RAILWAY_ENVIRONMENT=production`) unless `AUTH_DEMO_IN_PRODUCTION=1`;
  5 wrong codes lock a challenge; 5 starts per phone per hour; PIN, code and token are never logged; auth setup errors fail open (complaints are never blocked by a config mistake).
- Saved login: random token, **only its SHA-256 is stored**; sliding idle expiry (default 30 days, `AUTH_IDLE_DAYS`) with an absolute maximum (90 days, `AUTH_MAX_DAYS`);
  after that the citizen logs in again. Separate from the 30-minute chat timeout (S20). Bearer token in `localStorage`, not a cookie (site on Vercel, API on Railway).

## 4. API (additive)
`POST /api/v1/auth/start {phone}` -> `{challenge_id, provider, hint}` · `POST /auth/verify {challenge_id, code}` -> `{token, expires_at, phone_masked}` ·
`GET /auth/me` · `POST /auth/logout` (Bearer). New error codes: `AUTH_REQUIRED` (401), `AUTH_EXPIRED` (401), `AUTH_INVALID_CODE` (401), `AUTH_RATE_LIMITED` (429).
`/message` accepts `Authorization: Bearer`; new `ask_for` value `login`. Responses and logs carry only the **masked** phone (`+91 ••••••3210`).

## 5. Structured location
`location_details.parse()` (code, no LLM) turns "शाजापुर जिला, कालापीपल तहसील" into district (matched to the 55 official districts, Hindi/English/alternate spellings, `specs/registry/districts.yaml`),
tehsil and nearest place; "I don't know" is kept as unknown; everyday words that are also district names (सीधी, धार, सागर ...) need a marker or a very short answer. Stored as
ticket columns `district`, `tehsil`, `nearest_place`, `location_precision` (exact / village / district / unknown), plus the notes in `fields["_intake"]`.
This also fixed a bug: the district answer used to overwrite the village the citizen had named.

## 6. Database (migrations 002 additive and 003 cutover)
New tables `users`, `auth_challenges`, `auth_sessions`; new `tickets` columns `user_id`, `district`, `tehsil`, `nearest_place`, `location_precision`; RLS on, zero policies, grants revoked (same
as every table); a Human Evaluation desk office is INSERTED (General Triage is left alone, so an older server keeps working). **003 is the cutover** (moves General Triage tickets and offices to Human Evaluation): run it only when the new code is deployed. **Apply 002 before setting `AUTH_PROVIDER` / `AUTH_REQUIRED` / `INTAKE_V2` in a deployed environment.** Until then the backend
keeps working: ticket inserts retry without the new columns, auth endpoints answer 503, the dashboard falls back to the base columns. Untested against a real Postgres (written and statically checked only).

## 7. Human Evaluation rename
Spec `general.yaml` -> `human_evaluation.yaml` (service id `human_evaluation`, department "Human Evaluation", office "Human Evaluation Desk (DEMO)"); constant `GENERAL_SERVICE` ->
`HUMAN_EVALUATION_SERVICE`; dashboard role `triage` -> `evaluator` (demo account `evaluator.desk`). The LLM prompt now names `human_evaluation` as the "none of the others fits" id.

## 8. Not done / limits
- No real OTP provider, no Aadhaar, no SMS/WhatsApp notification, no "my complaints" page yet. The hidden full-chat page (`app.js`) was not given the login (it is not loaded by `index.html`).
- Phone numbers are personal data: consent text, a retention rule and access control for production are still to be decided (demo keeps them permanently).
- The officer sees the full number in the opened ticket; there is no audit of who viewed it yet (the dashboard writes only status / reassignment today).
- Checked in a browser against a stub backend (real routes and auth code, no database): login prompt at confirmation, wrong PIN message, correct PIN files the complaint, login survives a reload.

## ACCEPTANCE
- [x] Complaint without login -> `ask_for=login`, draft kept; after login the same confirmation files the ticket with `user_id`.
- [x] Without `AUTH_REQUIRED` complaints are filed exactly as before; a logged-in citizen is still linked.
- [x] Wrong / expired / over-attempted codes rejected with Hindi citizen-safe text; tokens stored hashed; demo PIN refused on production.
- [x] District / tehsil parsed and stored; "don't know" accepted and never re-asked; a missing database column never loses a complaint.
- [x] Officer sees the citizen's phone only in the opened ticket; list queries never select it.
