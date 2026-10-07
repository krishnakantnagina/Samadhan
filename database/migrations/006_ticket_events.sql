-- Migration 006: an audit trail for what officers do on the dashboard (who changed which ticket, who looked at a citizen's phone number).
-- ADDITIVE and safe to re-run. NOT applied automatically: run once on the Supabase database (SQL editor or psql).
-- Until it is applied the dashboards keep working: they log a warning and skip the audit write.
-- Security posture (S02 RULES 1): RLS on, no policies, grants revoked: only the server-side service key can touch it.

CREATE TABLE IF NOT EXISTS ticket_events (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  complaint_id  text NOT NULL,
  actor         text NOT NULL,           -- the dashboard account that did it (username), never the citizen
  action        text NOT NULL,           -- status_changed | reassigned | viewed_phone | viewed_ticket
  detail        text NULL,               -- e.g. 'new -> in_progress', or the reassign reason
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ticket_events_complaint_idx ON ticket_events (complaint_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ticket_events_actor_idx     ON ticket_events (actor, created_at DESC);

ALTER TABLE ticket_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ticket_events FROM anon, authenticated;
