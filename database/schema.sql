-- T03 — database schema, from docs/specs/S02-db-schema.md. Safe to re-run: IF NOT EXISTS / DO-block
-- guards throughout. Enums and RLS/grant hardening included here since they're schema-level, not
-- Supabase-project-level (that's T06). See docs/plans/T06-plan.md §T03 for the full plan.

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
  district       text NULL,               -- migration 005: English district name (specs/registry/districts.yaml); NULL = state-level desk
  active         bool NOT NULL DEFAULT true,
  UNIQUE (department, level, code)
);

CREATE UNIQUE INDEX IF NOT EXISTS offices_one_active_district_office
  ON offices (department, COALESCE(district, '')) WHERE level = 'district' AND active;

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

-- S02 RULES §1: RLS on, zero policies, AND grants explicitly revoked (docs/research/T06-research.md).
ALTER TABLE sessions           ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages           ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets            ENABLE ROW LEVEL SECURITY;
ALTER TABLE offices            ENABLE ROW LEVEL SECURITY;
ALTER TABLE routing_corrections ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON sessions, messages, tickets, offices, routing_corrections FROM anon, authenticated;
