-- Migration 005: offices belong to a district, so a complaint is routed to ITS district's office (not always the one Bhopal desk).
-- ADDITIVE and safe to re-run. NOT applied automatically: run once on the Supabase database (SQL editor or psql).
-- Until it is applied the backend keeps working exactly as before (jurisdiction falls back when offices.district is missing).
--
-- Before: a unique index allowed ONE active district office per department, and offices had no district, so every complaint from any of the 55 districts landed at
-- the same office. After: one active district office per (department, district), plus ward offices that know their district.
-- District names are the English names in specs/registry/districts.yaml (the same names the bot saves on a ticket), e.g. 'Bhopal', 'Rajgarh', 'Agar Malwa'.

ALTER TABLE offices ADD COLUMN IF NOT EXISTS district text NULL;

-- Everything seeded so far is the Bhopal demo data. The Human Evaluation desk stays district-less: it is the state-level queue.
UPDATE offices SET district = 'Bhopal' WHERE district IS NULL AND department <> 'Human Evaluation' AND department <> 'General Triage';

DROP INDEX IF EXISTS offices_one_active_district_per_department;
CREATE UNIQUE INDEX IF NOT EXISTS offices_one_active_district_office
  ON offices (department, COALESCE(district, ''))
  WHERE level = 'district' AND active;
CREATE INDEX IF NOT EXISTS offices_department_district_idx ON offices (department, district);

-- To add a real district desk (example):
--   INSERT INTO offices (department, level, code, name, aliases, office_name, officer_name, district, active)
--   VALUES ('Panchayat and Rural Development Department', 'district', 'PRD-RAJGARH', 'Rajgarh', ARRAY['Rajgarh'], 'Zila Panchayat CEO Office, Rajgarh', NULL, 'Rajgarh', true);
-- Ward / block offices of that district use the same district value and level 'ward' (or 'block').
