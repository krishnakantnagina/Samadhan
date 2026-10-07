# S38 Audit fixes (2026-10-07)

What changed after the full code audit (`local-research/AUDIT_2026-10-07.md`), and what must be done to the live system. Everything here is **off or inert until deployed**, and
migrations 005 and 006 are **not applied to any real database yet**.

## Database (run in this order in the Supabase SQL editor, once)
| Migration | What | Without it |
|---|---|---|
| `005_district_offices.sql` | `offices.district`; one district desk per (department, district) instead of one per department; existing rows become `Bhopal` | the backend keeps working as before (routing falls back to the single desk) |
| `006_ticket_events.sql` | audit trail table for dashboard actions (status change, reassign, who viewed a phone number) | the dashboards skip the audit write and log a warning |

| `007_district_desks.sql` | the desks: 38 departments x 55 districts and 11 state desks, from official district directories (`docs/DISTRICT_DESKS.md`, `docs/specs/S39-district-desks.md`) | complaints from outside Bhopal still go to the single Bhopal desk |

## Behaviour
- **District-aware routing (`app/jurisdiction.py`, `app/ticketing.py`):** a complaint goes to a ward of the citizen's district, else that district's office for the department, else the
  department's default desk marked `needs_review`. A place name is never matched across districts. GPS still works without a district.
- **Dashboards:** citizen text is escaped everywhere it is shown (`dashboard/src/dashboard/safe.py`); login lockout (5 wrong tries lock a username for 10 minutes, 40 across all names
  lock everything); audit trail with the officer's username; issue labels read from the specs (131 labels were missing and `other` always said "water"); a banner when more than 500 tickets
  exist and the lists are cut. New dependency: `pyyaml` (dashboard).
- **Cost and abuse (`app/ratelimit.py`):** per-IP and per-session limits (settings in `.env.example`); the website now fetches a reply's speech only when the citizen taps play (or for the
  reply to their own voice message); long replies are spoken in part (600 characters, cut at a sentence end).
- **Duplicates:** the same complaint text in the same chat within 3 minutes returns the existing ticket (`ticketing._existing_ticket`).
- **Website:** Hindi labels on the confirm card; 60 s timeout on messages, 25 s on speech, 20 s on login; privacy notice (`frontend/privacy.html`, DRAFT) linked from the greeting, login and pages.
- **Voice:** readers are told Hindi by default; the bot's last question reaches the reader; a storage failure no longer stops voice.
- **Operations:** API docs hidden on a production host; `/health/ready` checks the database; the container runs as a non-root user with a health check (**not built or tested here: no Docker**);
  `.github/workflows/ci.yml` runs lint and the three test suites on every push (**not run yet**).
- **Login:** only numbers starting 6-9 are accepted as mobiles; abandoned challenges are purged now and then.
- **Restart word:** a lone "दोबारा" or "शुरू" no longer wipes the draft.
- **Data removal (`app/data_rights.py`, `scripts/delete_citizen_data.py`):** removes a citizen's number, logins and recordings and unlinks their complaints (dry run unless `--yes`).

## Still open (needs a decision or an outside service)
- **Real OTP:** the demo PIN lets anyone log in as any number. Needs an SMS provider.
- **Privacy notice:** the text is a draft; the retention period and the contact address are placeholders for the project team and a legal adviser.
- **Free-tier limits:** Gemini embeddings (about 1,000 a day) and speech credit cannot carry real traffic.
- **Status lookup by number** is still open to anyone (sequential ids); a secret part of the id or a per-IP limit (now in place) is the next step.
- **Dashboard roles** are enforced in the screen only; real separation needs Supabase Auth with row-level security.
