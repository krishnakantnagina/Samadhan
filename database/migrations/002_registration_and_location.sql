-- 002 -- registration (S31), structured location (S31) and the Human Evaluation desk. ADDITIVE ONLY: nothing existing is renamed, changed or removed, so a
-- server still running the previous code keeps working. The General Triage -> Human Evaluation cutover is migrations/003 (run it when the new code is deployed).
-- NOT applied automatically. Run once against the Supabase database (psql or the SQL editor) AFTER schema.sql and the seeds. Safe to re-run: IF NOT EXISTS / guards.
-- Until it is applied the backend keeps working (ticket inserts fall back without the new columns, auth endpoints answer 503 unless AUTH_PROVIDER is set).
-- Security posture (S02 RULES 1): RLS on, zero policies, grants revoked: only the server-side service key can touch these tables.

-- 1. Registered citizens (phone). verified_by: demo | sms_otp | whatsapp | caller_id | ... (the Aadhaar number is NEVER stored: a future provider stores a reference key only)
CREATE TABLE IF NOT EXISTS users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone         text NOT NULL UNIQUE,
  verified_by   text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now()
);

-- 2. Login attempts in progress (PIN / OTP challenges)
CREATE TABLE IF NOT EXISTS auth_challenges (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone       text NOT NULL,
  provider    text NOT NULL,
  attempts    int  NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS auth_challenges_phone_created_idx ON auth_challenges (phone, created_at DESC);

-- 3. Saved logins: only the SHA-256 of the token is stored. Sliding idle expiry plus an absolute maximum.
CREATE TABLE IF NOT EXISTS auth_sessions (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               uuid NOT NULL REFERENCES users (id),
  token_hash            text NOT NULL UNIQUE,
  created_at            timestamptz NOT NULL DEFAULT now(),
  last_seen_at          timestamptz NOT NULL DEFAULT now(),
  idle_expires_at       timestamptz NOT NULL,
  absolute_expires_at   timestamptz NOT NULL,
  revoked               bool NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS auth_sessions_user_idx ON auth_sessions (user_id);

-- 4. Tickets: who filed it (the officer calls back on this number) and structured location for analysis.
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS user_id            uuid REFERENCES users (id);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS district           text;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS tehsil             text;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS nearest_place      text;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS location_precision text;
DO $$ BEGIN
  ALTER TABLE tickets ADD CONSTRAINT tickets_location_precision_check CHECK (location_precision IS NULL OR location_precision IN ('exact', 'village', 'district', 'unknown'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS tickets_district_idx ON tickets (district);
CREATE INDEX IF NOT EXISTS tickets_user_idx     ON tickets (user_id);

-- 5. Security: same rule as every other table.
ALTER TABLE users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_sessions   ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON users, auth_challenges, auth_sessions FROM anon, authenticated;

-- 6. The Human Evaluation desk: a district-level office so complaints the AI cannot place have somewhere to land (a queue, not a government department).
--    The old 'General Triage' rows are left untouched here.
INSERT INTO offices (department, level, code, name, aliases, centroid_lat, centroid_lng, office_name, officer_name, active)
VALUES ('Human Evaluation', 'district', 'HE-HQ', 'Bhopal', ARRAY['Bhopal'], NULL, NULL, 'Human Evaluation Desk (DEMO)', NULL, true)
ON CONFLICT (department, level, code) DO NOTHING;
