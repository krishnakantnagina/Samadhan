# T06 Research — Supabase Setup

Research only. No code, SQL, or Supabase project created. Checked 27 Sep 2026 against
supabase.com's current docs (Supabase's SQL/CLI/RLS/storage surface changes across versions —
this is not answered from training-data memory).

Context checked against: `docs/specs/S02-db-schema.md` (RULES section), `database/schema.sql`
and `database/seed.sql` (both currently **empty** — T03 is unchecked, nothing live exists yet),
`backend/pyproject.toml` (no `supabase` package listed as a dependency yet — T06/T14 will add it),
`.env.example` (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY` already named).

---

## 1. Running `schema.sql` + `seed.sql` on a new project

| Fact | Source | Date checked | Confidence |
|---|---|---|---|
| Recommended path: CLI-managed migrations (`supabase/migrations/*.sql`), tested locally with `supabase db reset`, then deployed with `supabase db push` | [Database Migrations](https://supabase.com/docs/guides/deployment/database-migrations) | 27 Sep 2026 | High |
| Pasting SQL directly into the dashboard SQL Editor on the **remote** project is explicitly discouraged: it bypasses migration history and makes a later `db push` fail with sync errors | [Database Migrations](https://supabase.com/docs/guides/deployment/database-migrations) | 27 Sep 2026 | High |
| `supabase db push --include-seed` exists and pushes seed data from config alongside migrations | [`supabase db push` CLI reference](https://supabase.com/docs/reference/cli/supabase-db-push) | 27 Sep 2026 | High |
| Locally, `supabase/seed.sql` is executed automatically on `supabase start` and every `supabase db reset`, always *after* migrations run | [Seeding your database](https://supabase.com/docs/guides/local-development/seeding-your-database) | 27 Sep 2026 | High |
| On a **remote/hosted** project, seed files do not run automatically as part of normal deploys — you must pass `--include-seed` explicitly | [`supabase db push` CLI reference](https://supabase.com/docs/reference/cli/supabase-db-push) | 27 Sep 2026 | High |
| Direct `psql` connection to the remote Postgres instance is possible (`supabase db push --db-url <connection-string>` or a raw `psql` session) but is the CLI reference's power-user path, not its headline recommendation for a small team | [`supabase db push` CLI reference](https://supabase.com/docs/reference/cli/supabase-db-push) | 27 Sep 2026 | Medium — page documents the flag; doesn't frame it as "recommended for small teams," that framing is mine |

**Recommendation for this team (2 people, no CI):** put `database/schema.sql` under
`supabase/migrations/<timestamp>_init.sql` (or point the CLI's `sql_paths` at the existing
`database/` layout — not checked whether that's supported, see Questions below), run
`supabase db reset` locally to sanity-check, then `supabase db push --include-seed` against the
real project. Do **not** paste `schema.sql` into the dashboard SQL Editor on the remote project
if you ever intend to `db push` afterwards — pick one path, not both.

## 2. RLS with no public policies + verifying the anon key is blocked

| Fact | Source | Date checked | Confidence |
|---|---|---|---|
| Enabling RLS is a genuine default-deny: with RLS on and zero policies, no data is accessible through the API with the anon (publishable) key | [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security) | 27 Sep 2026 | High |
| **This is only true once table-level GRANTs are also handled.** Supabase's own docs state Postgres runs two independent checks — GRANTs (can the role run the operation at all) and RLS policies (which rows) — and that adding/enabling RLS "doesn't take grants back." New tables on a Supabase project are, by default, granted `select, insert, update, delete` to `anon` and `authenticated` via schema default privileges; enabling RLS alone does not revoke that grant | [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security) | 27 Sep 2026 | **High — this is a real gap against S02's stated rule, see below** |
| Supabase's own recommended verification method is automated **pgTAP** database tests: files under `supabase/tests/<table>_rls.test.sql`, run via `supabase test db`, asserting both denials (`throws_ok`) and allowed cases (`results_eq`, `is_empty`) | [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security) | 27 Sep 2026 | High |
| No dashboard-click or ad-hoc `curl`-with-anon-key check is documented as the *official* verification method — pgTAP is what the page itself points to | [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security) | 27 Sep 2026 | Medium — absence of a simpler official method isn't the same as one not existing anywhere, it's just not what this page recommends |

**A manual smoke test is still possible** even without pgTAP: a REST call to
`{SUPABASE_URL}/rest/v1/<table>` with the `anon` key in the `apikey`/`Authorization` headers
should return an empty result set or a permission error once RLS+grants are both locked down.
NOT FOUND: an exact expected HTTP status/body for that call in Supabase's current docs — this is
inferred from general PostgREST/RLS behavior, not a quoted official example. Label this UNVERIFIED
until someone on the team actually runs it against a real project.

## 3. Private storage bucket + signed URLs

| Fact | Source | Date checked | Confidence |
|---|---|---|---|
| Python client method is `create_signed_url(path, expires_in, options=None)` (snake_case — not JS's `createSignedUrl`) | [Python: Create a signed URL](https://supabase.com/docs/reference/python/storage-from-createsignedurl) | 27 Sep 2026 | High |
| `expires_in` is required, in **seconds** (example: `60` = one minute) | [Python: Create a signed URL](https://supabase.com/docs/reference/python/storage-from-createsignedurl) | 27 Sep 2026 | High |
| Maximum allowed `expires_in` | — | 27 Sep 2026 | **NOT FOUND** — not stated on the fetched page |
| Bucket privacy is a property set at bucket-creation time (private vs. public); S02 already specifies the `audio` bucket is private | `docs/specs/S02-db-schema.md` (existing spec, not new research) | — | — |
| Exact Python method to *create* a bucket as private (e.g. `create_bucket(..., options={"public": False})`) | — | 27 Sep 2026 | **NOT FOUND** — not fetched/confirmed this session; only the signed-URL read path was verified, not bucket creation. Flagged as a follow-up, see Questions |

## 4. Calling a Postgres function from Python (one-transaction save)

| Fact | Source | Date checked | Confidence |
|---|---|---|---|
| Sync call: `supabase.rpc("function_name", {"arg1": "value1"}).execute()` | [Python: Call a Postgres function](https://supabase.com/docs/reference/python/rpc) | 27 Sep 2026 | High |
| Params are passed as a dict, second positional argument; `.execute()` is required to actually run it | [Python: Call a Postgres function](https://supabase.com/docs/reference/python/rpc) | 27 Sep 2026 | High |
| An **async** client exists and is official: `from supabase import acreate_client, AsyncClient` — resolves this project's own open question (S04 `G-S04-2`/`D-S04-2`, deferred to T14) of whether sync-or-async is even a real choice: both are documented, it's a genuine pick, not a gap in the SDK | [Supabase Python client support](https://supabase.com/blog/python-support) + [github.com/orgs/supabase/discussions/37052](https://github.com/orgs/supabase/discussions/37052) (non-official, corroborating) | 27 Sep 2026 | Medium-high — the async client's existence is corroborated by two sources, but I did not fetch the official Python RPC page's own async example directly, only the sync one |
| How a Postgres function's exception/error surfaces to Python (exception type, error shape) | — | 27 Sep 2026 | **NOT FOUND** — the fetched RPC reference page doesn't document this; needs `try`/`except` testing against a real function once one exists |
| `supabase` is the current pip package name (`pip install supabase`) | [Python: Initializing](https://supabase.com/docs/reference/python/initializing) | 27 Sep 2026 | High |

**Relevance to this project's "one transaction" goal:** an RPC call to a Postgres function is
exactly the mechanism for atomically doing session-update + message-insert + (sometimes)
ticket-create in one round trip — a single Postgres function wrapping those three writes in one
implicit transaction, invoked once via `.rpc(...).execute()`. This is S10/S06's design question
(not T06's), noted here only because it's what T06 unlocks.

## 5. Free-tier limits that could bite before 10 Oct 2026

| Limit | Value | Source | Date checked | Confidence |
|---|---|---|---|---|
| Free projects paused after inactivity | **7 days** ("1 week") of low database activity | [supabase.com/pricing](https://supabase.com/pricing) + [Going into prod](https://supabase.com/docs/guides/platform/going-into-prod) ("We may pause applications on the Free Plan that exhibit low activity in a 7-day period") | 27 Sep 2026 | High |
| Paused project recovery | Restorable from the Supabase dashboard | [Going into prod](https://supabase.com/docs/guides/platform/going-into-prod) | 27 Sep 2026 | High |
| Guaranteed no pausing | Only on the paid Pro plan | [Going into prod](https://supabase.com/docs/guides/platform/going-into-prod) | 27 Sep 2026 | High |
| Database size | 500 MB (shared CPU, 500 MB RAM compute) | [supabase.com/pricing](https://supabase.com/pricing) | 27 Sep 2026 | High |
| File storage | 1 GB | [supabase.com/pricing](https://supabase.com/pricing) | 27 Sep 2026 | High |
| Egress/bandwidth | 5 GB egress + 5 GB cached egress | [supabase.com/pricing](https://supabase.com/pricing) | 27 Sep 2026 | High |
| Active project limit | 2 active free projects per account | [supabase.com/pricing](https://supabase.com/pricing) | 27 Sep 2026 | High |
| Row-count limit | — | — | 27 Sep 2026 | **NOT FOUND** — Supabase's official pricing page states storage in MB/GB, not a row count; no official row cap was found. (Third-party estimates exist but are explicitly out — see Rules) |

**This is the sharpest real risk for this project's timeline.** PROJECT.md says nothing changes
in the code after 30 Sep noon submission until the event ends 10 Oct — a gap of up to 10 days.
"Inactivity" per the official page is about database activity, not dashboard visits; a Supabase
project that receives no queries in that window is a real candidate for auto-pause going into the
live demo. This needs a plan (see Questions).

---

## VERIFIED vs UNVERIFIED

| # | Item | Status |
|---|---|---|
| 1 | `supabase db push --include-seed` deploys migrations + seed to remote | VERIFIED (official CLI reference) |
| 2 | Dashboard SQL Editor edits to a remote DB break future `db push` | VERIFIED (official migrations guide) |
| 3 | RLS + zero policies alone is NOT sufficient; default grants to `anon`/`authenticated` must be explicitly revoked | VERIFIED (official RLS guide) — **this is the one that needs the team's attention, see below** |
| 4 | pgTAP (`supabase test db`) is Supabase's own recommended RLS verification method | VERIFIED (official RLS guide) |
| 5 | A simple anon-key REST call returning empty/error as an ad-hoc smoke test | UNVERIFIED — inferred behavior, not a quoted official example |
| 6 | `create_signed_url(path, expires_in, options=None)`, `expires_in` in seconds | VERIFIED (official Python storage reference) |
| 7 | Max signed-URL expiry | UNVERIFIED / NOT FOUND |
| 8 | Python bucket-creation call for a private bucket | UNVERIFIED / NOT FOUND — not fetched this session |
| 9 | `.rpc(name, params).execute()` sync pattern | VERIFIED (official Python RPC reference) |
| 10 | Official async client (`acreate_client`/`AsyncClient`) exists | VERIFIED via Supabase's own blog post; the specific async RPC code example itself was not independently fetched, so treat the *existence* as verified and the *exact async RPC syntax* as UNVERIFIED |
| 11 | Free plan: 7-day inactivity pause, 500 MB DB, 1 GB storage, 5 GB egress, 2 active projects | VERIFIED (official pricing page + official "going into prod" guide) |
| 12 | Postgres-function error shape surfacing to Python | NOT FOUND |

---

## Questions for the team

1. **RLS + grants (the biggest one).** S02's RULES section says "RLS enabled on all tables with no
   public policies → anon key has zero access," stated as if RLS alone does it. Supabase's own
   current docs say that's only true once default grants to `anon`/`authenticated` are also
   revoked. Someone needs to check, on the actual project once T03/T06 exist, whether newly
   created tables via a plain `CREATE TABLE` in a migration inherit any grant to `anon` at all, or
   whether that default-grant behavior is specific to tables made through the Supabase dashboard's
   Table Editor. If migrations-only tables don't get an automatic `anon` grant, S02's rule is fine
   as written; if they do, `schema.sql`/the migration needs an explicit `REVOKE ALL ... FROM anon,
   authenticated` per table, or S02 needs a line added. This should be resolved with a real check
   (or the pgTAP test suite) before trusting the "anon key has zero access" claim in production.
2. **Migrations vs. dashboard SQL Editor.** Given no CI exists, do we commit to CLI-managed
   migrations (`supabase/migrations/`) as the only way `schema.sql`/`seed.sql` ever reach the
   remote project, or is a one-time SQL-Editor paste acceptable for the hackathon timeline as long
   as nobody runs `db push` afterward? Pick one — mixing them is what breaks, per the docs above.
3. **Free-tier pause risk across 30 Sep–10 Oct.** Do we (a) upgrade to Pro before the freeze so the
   project can't pause, (b) schedule a periodic no-op query to keep it "active," or (c) accept the
   risk and add "restore from dashboard, it's a manual click" to the demo-day checklist (T47/T49)?
   This should be decided before the freeze, not discovered on 8 Oct during rehearsal.
4. **Bucket creation and max signed-URL expiry** were not confirmed this session (see NOT FOUND
   items #7, #8) — whoever implements T06 needs to fetch
   [supabase.com/docs/reference/python/storage-createbucket](https://supabase.com/docs/reference/python/storage-createbucket)
   (not fetched, guessed path only, verify the URL itself) or search the current docs directly
   before writing that code.
5. **Sync or async Supabase client** (S04 `G-S04-2`, needed before T14): now that both are
   confirmed to exist officially, this is a real team decision, not a "wait and see if the SDK
   supports it" question. The rest of `backend/` (FastAPI's `main.py`, S06/S10) is written
   synchronously so far (see `T07-plan.md`) — recommend sync `create_client` for consistency unless
   Realtime features are needed, since the docs note "Realtime in Python only works with the
   asynchronous client" and this project has no Realtime requirement in scope.

## What conflicts with S02, if anything

- **Direct conflict (needs resolution, see Question 1 above):** S02's RULES §1 states RLS-enabled
  + no-public-policies is sufficient for "anon key has zero access." Supabase's current official
  docs treat that as necessary but not sufficient — grants matter independently. S02 isn't wrong
  about the *intent*, but the *mechanism* it implies (RLS alone) doesn't match how Supabase's
  Postgres layer actually enforces access as of the pages fetched today. Recommend either adding
  an explicit grant-revocation step to S02/`schema.sql`, or explicitly confirming (via pgTAP or a
  manual anon-key test) that it's a non-issue for this project's table-creation method before
  relying on it.
- **No conflict, just a process note:** S02 §"RULES (security)" rule 5 says seed data "lives in
  `database/seed.sql` so the DB can be rebuilt in one run." That's still true locally
  (`supabase db reset` runs migrations then seed in one command), but on the **remote** project
  it's two explicit choices (`db push` + `--include-seed`), not fully automatic. Doesn't
  contradict S02, just means "one run" is a local-dev claim, not a remote one.
- **No conflict found** for the storage-bucket path (S02's `audio` bucket, private, signed URLs)
  or the RPC-for-one-transaction idea — both align with what's officially documented, subject to
  the NOT FOUND gaps above being filled in before T06 is actually implemented.
