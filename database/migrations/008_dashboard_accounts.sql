-- Migration 008: dashboard logins that belong to a DESK (an office / post), kept in the database so they survive a redeploy and can be handed over when an officer is transferred.
-- ADDITIVE and safe to re-run. NOT applied automatically: run once on the Supabase database (SQL editor or psql).
-- Until it is applied the dashboards keep working with the shared admin login and the accounts file only; the "Desk access" screen says the table is missing.
--
-- Why: a complaint goes to an office, never to a person (offices change hands). A login is the key to a desk: the CM office gives it, takes it away or replaces it when the officer changes,
-- and no ticket is touched. Only a salted PBKDF2 hash is stored, never the password. Security posture (S02 RULES 1): RLS on, no policies, grants revoked: only the server-side service key can use it.

CREATE TABLE IF NOT EXISTS dashboard_accounts (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username      text NOT NULL,
  role          text NOT NULL CHECK (role IN ('cm_admin', 'dept_head', 'office_officer', 'evaluator')),
  department    text NULL,                 -- the ticket department text (tickets.department): dept_head and office_officer
  office_name   text NULL,                 -- the desk (offices.office_name = tickets' office name): office_officer
  dept_id       text NULL,                 -- registry id of the department (optional)
  label         text NOT NULL DEFAULT '',  -- free text: who holds it now, for the CM office's own reference
  salt          text NOT NULL,
  hash          text NOT NULL,
  iterations    int  NOT NULL,
  active        bool NOT NULL DEFAULT true,
  must_change   bool NOT NULL DEFAULT true, -- a new or reset password is temporary: the holder must choose their own at the first login
  created_by    text NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS dashboard_accounts_username_idx ON dashboard_accounts (lower(username));
CREATE INDEX IF NOT EXISTS dashboard_accounts_office_idx ON dashboard_accounts (office_name) WHERE active;

-- Who gave, took away, replaced or reset which login (the history the department can ask for).
CREATE TABLE IF NOT EXISTS dashboard_account_events (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username    text NOT NULL,
  action      text NOT NULL,   -- created | password_reset | password_changed | disabled | enabled | handed_over
  actor       text NOT NULL,   -- the dashboard account that did it
  detail      text NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS dashboard_account_events_user_idx ON dashboard_account_events (username, created_at DESC);

ALTER TABLE dashboard_accounts       ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_account_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON dashboard_accounts, dashboard_account_events FROM anon, authenticated;
