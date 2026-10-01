-- S28 multi-department routing (29 Sep 2026): DEMO offices for the extra departments.
-- EVERYTHING here is DEMO data, like the water wards in seed.sql (docs/specs/S09-jurisdiction.md): the department names are the
-- real government department types, but the office rows are constructed for the demo and are NOT sourced from any government
-- list. Ward names/aliases repeat seed.sql so a place name routes the same way in every department. Centroids stay NULL (S09).
-- Safe to run twice: ON CONFLICT on (department, level, code) is a no-op.

INSERT INTO offices (department, level, code, name, aliases, centroid_lat, centroid_lng, office_name, officer_name, active)
SELECT d.department, 'ward', w.code, w.name, w.aliases, NULL, NULL,
       'Ward ' || w.name || ' ' || d.short || ' Office (DEMO)', NULL, true
FROM (VALUES
  ('Bijli Vibhag',           'Bijli'),
  ('Lok Nirman Vibhag',      'PWD'),
  ('Nagar Nigam Sanitation', 'Sanitation')
) AS d(department, short)
CROSS JOIN (VALUES
  ('1',  'महात्मा गांधी',  ARRAY['Mahatma Gandhi']),
  ('24', 'रानी कमलापति',   ARRAY['Rani Kamlapati', 'Habibganj']),
  ('52', 'मिसरोद',         ARRAY['Misrod']),
  ('60', 'गोविंदपुरा',     ARRAY['Govindpura']),
  ('80', 'सर्वधर्म कोलार', ARRAY['Sarvadharm Kolar', 'Kolar Road'])
) AS w(code, name, aliases)
ON CONFLICT (department, level, code) DO NOTHING;

-- One district fallback office per department (required by the resolver; routing falls back here when no ward matches).
INSERT INTO offices (department, level, code, name, aliases, centroid_lat, centroid_lng, office_name, officer_name, active)
VALUES
  ('Bijli Vibhag',           'district', 'ELEC-HQ',  'Bhopal', ARRAY['Bhopal'], NULL, NULL, 'Bijli Vibhag District Office (DEMO)',      NULL, true),
  ('Lok Nirman Vibhag',      'district', 'PWD-HQ',   'Bhopal', ARRAY['Bhopal'], NULL, NULL, 'Lok Nirman Vibhag District Office (DEMO)', NULL, true),
  ('Nagar Nigam Sanitation', 'district', 'SAN-HQ',   'Bhopal', ARRAY['Bhopal'], NULL, NULL, 'Nagar Nigam Sanitation Office (DEMO)',     NULL, true),
  ('Human Evaluation',       'district', 'HE-HQ',    'Bhopal', ARRAY['Bhopal'], NULL, NULL, 'Human Evaluation Desk (DEMO)',             NULL, true)
ON CONFLICT (department, level, code) DO NOTHING;
