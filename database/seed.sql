-- T05 pilot jurisdiction data. Water supply only, Bhopal. See docs/specs/S09-jurisdiction.md
-- and docs/plans/T05-plan.md for VERIFIED/DEMO status per value — do not add rows here without
-- updating both.
-- Safe to run twice: ON CONFLICT on the (department, level, code) unique constraint (S02) is a no-op.

INSERT INTO offices (department, level, code, name, aliases, centroid_lat, centroid_lng, office_name, officer_name, active)
VALUES
  ('Jal Vibhag', 'ward', '1',  'महात्मा गांधी',   ARRAY['Mahatma Gandhi'],              NULL, NULL, 'Ward महात्मा गांधी Office',   NULL, true),
  ('Jal Vibhag', 'ward', '24', 'रानी कमलापति',    ARRAY['Rani Kamlapati', 'Habibganj'], NULL, NULL, 'Ward रानी कमलापति Office',    NULL, true),
  ('Jal Vibhag', 'ward', '52', 'मिसरोद',          ARRAY['Misrod'],                     NULL, NULL, 'Ward मिसरोद Office',          NULL, true),
  ('Jal Vibhag', 'ward', '60', 'गोविंदपुरा',      ARRAY['Govindpura'],                 NULL, NULL, 'Ward गोविंदपुरा Office',      NULL, true),
  ('Jal Vibhag', 'ward', '80', 'सर्वधर्म कोलार',  ARRAY['Sarvadharm Kolar', 'Kolar Road'], NULL, NULL, 'Ward सर्वधर्म कोलार Office', NULL, true),
  ('Jal Vibhag', 'district', 'BMC-HQ', 'Bhopal', ARRAY['BMC', 'Bhopal Municipal Corporation', 'Bhopal Nagar Nigam'], NULL, NULL, 'BMC Head Office', NULL, true)
ON CONFLICT (department, level, code) DO NOTHING;
