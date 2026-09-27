# Plan: T03 (schema) → T05 (seed) → T06 (Supabase setup)

T06 depends on T03 (`docs/TICKETS.md`'s own dependency column) and T05. `database/schema.sql` is
currently empty, so this plan does T03 first, as its own explicit step with its own acceptance
check and its own commit — not folded silently into T06. Order: **T03 → T05 → T06**.

---

## T03 — `database/schema.sql` (from S02, prerequisite)

Built strictly from `docs/specs/S02-db-schema.md`, including the approved change (`officer_name`
nullable). Nothing beyond S02 is added except two things S02 itself requires but doesn't spell out
as DDL — noted inline below, not new business rules:

- A **partial unique index** so "exactly one active `district` row per department" (S02, `offices`)
  is actually enforced by Postgres, not just written as prose.
- **`REVOKE ALL ... FROM anon, authenticated`** on every table, alongside `ENABLE ROW LEVEL
  SECURITY`. This directly resolves the conflict `docs/research/T06-research.md` flagged: Supabase's
  own current docs say RLS-with-no-policies alone does **not** guarantee anon has zero access —
  default grants are a separate, independent check that RLS doesn't revoke. Revoking them explicitly
  in the schema is how S02's rule 1 ("anon key has zero access") actually holds, not just RLS alone.

`complaint_id` is a **generated column** (`'SMD-' || lpad(id::text, 4, '0')`), not app-computed —
`lpad` only pads up to 4 chars and leaves a longer number untouched, so it satisfies S02's own
acceptance line "ID 10000 renders as SMD-10000" for free, with no separate app-level formatting
code to get wrong.

```sql
-- T03 — database schema, from docs/specs/S02-db-schema.md. Safe to re-run: IF NOT EXISTS / DO-block
-- guards throughout. Enums and RLS/grant hardening included here since they're schema-level, not
-- Supabase-project-level (that's T06).

DO $$ BEGIN
  CREATE TYPE ticket_status AS ENUM ('new', 'in_progress', 'resolved', 'needs_review');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE session_status AS ENUM ('active', 'completed', 'cancelled', 'expired');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE SEQUENCE IF NOT EXISTS complaint_seq;

CREATE TABLE IF NOT EXISTS sessions (
  id                     uuid PRIMARY KEY,
  status                 session_status NOT NULL DEFAULT 'active',
  service_id             text NULL,
  collected_fields       jsonb NOT NULL DEFAULT '{}',
  awaiting_confirmation  bool NOT NULL DEFAULT false,
  lat                    float8 NULL,
  lng                    float8 NULL,
  created_at             timestamptz NOT NULL DEFAULT now(),
  last_active_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS offices (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  department     text NOT NULL,
  level          text NOT NULL CHECK (level IN ('ward', 'zone', 'municipal_corp', 'gram_panchayat', 'block', 'district')),
  code           text NOT NULL,
  name           text NOT NULL,
  aliases        text[] NOT NULL DEFAULT '{}',
  centroid_lat   float8 NULL,
  centroid_lng   float8 NULL,
  office_name    text NOT NULL,
  officer_name   text NULL,               -- S02 change: NULL where no verified role exists (S09)
  active         bool NOT NULL DEFAULT true,
  UNIQUE (department, level, code)
);

CREATE UNIQUE INDEX IF NOT EXISTS offices_one_active_district_per_department
  ON offices (department) WHERE level = 'district' AND active;

CREATE TABLE IF NOT EXISTS messages (
  message_id   uuid NOT NULL,
  session_id   uuid NOT NULL REFERENCES sessions (id),
  input_type   text NOT NULL CHECK (input_type IN ('text', 'audio', 'location')),
  text         text NULL,
  transcript   text NULL,
  audio_path   text NULL,
  response     jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (session_id, message_id)
);

CREATE TABLE IF NOT EXISTS tickets (
  id                  bigint PRIMARY KEY DEFAULT nextval('complaint_seq'),
  complaint_id        text GENERATED ALWAYS AS ('SMD-' || lpad(id::text, 4, '0')) STORED,
  session_id          uuid NOT NULL REFERENCES sessions (id),
  service_id          text NOT NULL,
  department          text NOT NULL,
  office_id           bigint NOT NULL REFERENCES offices (id),
  status              ticket_status NOT NULL DEFAULT 'new',
  fields              jsonb NOT NULL,
  summary_en          text NOT NULL,
  original_text       text NOT NULL,
  audio_path          text NULL,
  lat                 float8 NULL,
  lng                 float8 NULL,
  routing_confidence  numeric(3, 2) NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT tickets_complaint_id_unique UNIQUE (complaint_id)
);

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tickets_touch_updated_at ON tickets;
CREATE TRIGGER tickets_touch_updated_at BEFORE UPDATE ON tickets
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE IF NOT EXISTS routing_corrections (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ticket_id       bigint NOT NULL REFERENCES tickets (id),
  from_office_id  bigint NOT NULL REFERENCES offices (id),
  to_office_id    bigint NOT NULL REFERENCES offices (id),
  reason          text NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (from_office_id <> to_office_id)
);

CREATE INDEX IF NOT EXISTS tickets_status_idx      ON tickets (status);
CREATE INDEX IF NOT EXISTS tickets_department_idx  ON tickets (department);
CREATE INDEX IF NOT EXISTS tickets_created_at_idx  ON tickets (created_at DESC);
CREATE INDEX IF NOT EXISTS messages_session_idx    ON messages (session_id, created_at);
CREATE INDEX IF NOT EXISTS sessions_last_active_idx ON sessions (last_active_at);

-- S02 RULES §1: RLS on, zero policies, AND grants explicitly revoked (see note above).
ALTER TABLE sessions           ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages           ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets            ENABLE ROW LEVEL SECURITY;
ALTER TABLE offices            ENABLE ROW LEVEL SECURITY;
ALTER TABLE routing_corrections ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON sessions, messages, tickets, offices, routing_corrections FROM anon, authenticated;
```

### T03 acceptance (from S02's own list, the schema-only items)

| S02 acceptance item | Satisfied by |
|---|---|
| `schema.sql` runs cleanly on a fresh Supabase project | Every `CREATE` is `IF NOT EXISTS`/DO-guarded; runs standalone |
| Two tickets created concurrently get different `complaint_id`s; ID 10000 renders as `SMD-10000` | `complaint_seq` + generated `complaint_id` column (`lpad` doesn't truncate) |
| Same `(session_id, message_id)` twice fails on PK; same `message_id` under a different session is accepted | `messages` composite PK `(session_id, message_id)` |
| Anon key cannot read any table | `ENABLE ROW LEVEL SECURITY` + `REVOKE ALL ... FROM anon, authenticated` on all 5 tables |
| Status change updates `updated_at` automatically | `tickets_touch_updated_at` trigger |
| Reassignment writes one `routing_corrections` row and changes `tickets.office_id` | Schema supports it; the actual reassign logic is the dashboard's (out of scope here) |

**Commit (separate from T06):** `T03: database schema from S02`

---

## T05 — seed data (already planned)

See `docs/plans/T05-plan.md` in full. Run its `INSERT` block (idempotent, `ON CONFLICT DO
NOTHING`) immediately after T03's schema, before any T06 verification below — several T06 checks
(anon-key test, RLS smoke test) are more convincing with real rows in `offices` to try to read.

---

## T06 — Supabase project setup

Split by who can actually do each step — I have no Supabase account access.

### You do (dashboard / account)

1. **Create the project** (if not already done): supabase.com/dashboard → New project → note the
   **Project URL** and, under Project Settings → API, the **anon (publishable) key** and
   **service_role (secret) key**.
2. **Put keys in your local `.env`** (copy `.env.example` → `.env` if you haven't): `SUPABASE_URL`,
   `SUPABASE_SERVICE_KEY` (service_role — backend/dashboard only), `SUPABASE_ANON_KEY`. Never paste
   these into chat or a commit — `.env` is already gitignored.
3. **Deploy schema + seed.** Recommended (per `docs/research/T06-research.md` §1): install the
   Supabase CLI, `supabase link` to the project, put T03's SQL under
   `supabase/migrations/<timestamp>_init.sql` and T05's under the seed config, then:
   ```bash
   supabase db push --include-seed
   ```
   Do **not** also paste the same SQL into the dashboard's SQL Editor afterward — mixing the two
   breaks migration history (research §1). If you'd rather skip the CLI for the hackathon timeline,
   a one-time SQL Editor paste of T03 then T05 is the fallback — but then commit to *never* running
   `db push` against this project afterward, per the same research note.
4. **Create the private storage bucket**, click-by-click: dashboard → **Storage** (left sidebar) →
   **New bucket** → name it exactly `audio` → leave **Public bucket** unchecked → **Save**.
5. Reply **"done"** after each of steps 1–4 so I know to move on (per the global rule: I wait for
   you on dashboard steps).

### I do (repo)

6. Confirm `.env.example` already lists `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
   `SUPABASE_ANON_KEY` (it does, from T02) — no new entries needed.
7. Give you the exact anon-key test to run (below) and record whatever result you paste back into
   this plan's build log — I never see or need the key itself, only the HTTP status/body.

### The anon-key test (T06 research flagged the exact response as officially undocumented — this
/ empirically settles it for this project)

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "$SUPABASE_URL/rest/v1/offices?select=*" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Authorization: Bearer $SUPABASE_ANON_KEY"
```
Expected: a non-200 status (likely `401` with a "permission denied" body) now that grants are
revoked in T03 — not a `200` with an empty array, which would only mean RLS filtered rows while
still technically permitting the query. Run it, tell me the status code (and body if it's not
obviously sensitive); if it comes back `200`, something in T03's `REVOKE` didn't take and we stop
and look at it together, per the global rule.

### Mapping to S02 acceptance (T06-specific items)

| S02 acceptance item | Satisfied by |
|---|---|
| `schema.sql` + `seed.sql` run cleanly on a fresh Supabase project | Steps 3 (dashboard action) |
| Anon key cannot read any table or audio file | T03's `REVOKE`/RLS + the curl test above; bucket privacy (step 4) covers the audio file half |

**Commit:** `T06: Supabase setup` (repo-side files only — `.env.example` if changed, this plan's
build-log update; the actual Supabase project has no git representation)

---

## Build order

**T03 (schema) → T05 (seed) → T06 (RLS verification, storage bucket, keys).** Each gets its own
commit; `docs/TICKETS.md` gets T03, T05, and T06 ticked separately, not as one entry.
