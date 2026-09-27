-- T20 -- 15 demo tickets for dashboard development/testing (T23/T24).
-- Spec: docs/TICKETS.md T20 ("Rows visible"). Depends on T03 (schema.sql) + T05 (seed.sql, office
-- data) already applied.
--
-- These are SYNTHETIC example complaints -- same convention as the mock's own SMD-0042/SMD-0007
-- (backend/mock/app.py) and T09's planned test sentences: written by the team to exercise the
-- dashboard, not real citizen data. This is distinct from T05's office data, which had to be real
-- (VERIFIED) or explicitly labeled DEMO -- a synthetic ticket doesn't claim to be a real complaint,
-- so no VERIFIED/DEMO labeling is needed here.
--
-- routing_confidence values are kept consistent with what the real S09 resolver can actually
-- produce (backend/app/jurisdiction.py): 1.00 for a GPS match, >=0.80 for a name match (S09's own
-- 80-point cutoff), or exactly 0.00 for a fallback (no match / a tie) -- never an in-between value
-- a real request could not generate.
--
-- Safe to re-run: each INSERT is guarded by a WHERE NOT EXISTS on its own synthetic session_id, so
-- running this file twice does not create duplicate tickets or sessions.

-- Synthetic sessions (FK target for tickets.session_id). One per ticket, already 'completed'
-- since the (synthetic) conversation ended in a submitted ticket. collected_fields/lat/lng mirror
-- what that session would have held right before submission.

INSERT INTO sessions (id, status, service_id, collected_fields, awaiting_confirmation, lat, lng, created_at, last_active_at) VALUES
  ('00000000-0000-4000-8000-000000000001', 'completed', 'water_supply', '{"issue_type":"no_supply","location":"वार्ड 1","duration_days":3,"address_detail":"वार्ड कार्यालय के पास"}', false, NULL, NULL, '2026-09-28 08:05:00+00', '2026-09-28 08:10:00+00'),
  ('00000000-0000-4000-8000-000000000002', 'completed', 'water_supply', '{"issue_type":"leakage","location":"महात्मा गांधी वार्ड","duration_days":1}', false, NULL, NULL, '2026-09-26 10:00:00+00', '2026-09-26 10:05:00+00'),
  ('00000000-0000-4000-8000-000000000003', 'completed', 'water_supply', '{"issue_type":"low_pressure","location":"Habibganj","duration_days":5,"address_detail":"हबीबगंज स्टेशन के पास"}', false, NULL, NULL, '2026-09-28 07:35:00+00', '2026-09-28 07:40:00+00'),
  ('00000000-0000-4000-8000-000000000004', 'completed', 'water_supply', '{"issue_type":"dirty_water","duration_days":2}', false, 23.2493, 77.4230, '2026-09-25 14:15:00+00', '2026-09-25 14:20:00+00'),
  ('00000000-0000-4000-8000-000000000005', 'completed', 'water_supply', '{"issue_type":"no_supply","location":"मिसरोद","duration_days":7,"address_detail":"मिसरोद बस स्टैंड के पास"}', false, NULL, NULL, '2026-09-28 06:50:00+00', '2026-09-28 06:55:00+00'),
  ('00000000-0000-4000-8000-000000000006', 'completed', 'water_supply', '{"issue_type":"other","location":"Misrod","address_detail":"टंकी के पास अजीब गंध"}', false, NULL, NULL, '2026-09-26 18:25:00+00', '2026-09-26 18:30:00+00'),
  ('00000000-0000-4000-8000-000000000007', 'completed', 'water_supply', '{"issue_type":"leakage","location":"गोविंदपुरा","duration_days":2}', false, NULL, NULL, '2026-09-24 08:55:00+00', '2026-09-24 09:00:00+00'),
  ('00000000-0000-4000-8000-000000000008', 'completed', 'water_supply', '{"issue_type":"low_pressure","location":"Govindpura","duration_days":10,"address_detail":"गोविंदपुरा औद्योगिक क्षेत्र"}', false, NULL, NULL, '2026-09-28 09:15:00+00', '2026-09-28 09:20:00+00'),
  ('00000000-0000-4000-8000-000000000009', 'completed', 'water_supply', '{"issue_type":"dirty_water","location":"Kolar Road","duration_days":4,"address_detail":"कोलार रोड, सर्वधर्म कॉलोनी"}', false, NULL, NULL, '2026-09-27 15:05:00+00', '2026-09-27 15:10:00+00'),
  ('00000000-0000-4000-8000-000000000010', 'completed', 'water_supply', '{"issue_type":"no_supply","duration_days":1}', false, 23.2156, 77.4384, '2026-09-28 10:00:00+00', '2026-09-28 10:05:00+00'),
  ('00000000-0000-4000-8000-000000000011', 'completed', 'water_supply', '{"issue_type":"no_supply","location":"नयापुरा","duration_days":6}', false, NULL, NULL, '2026-09-27 11:55:00+00', '2026-09-27 12:00:00+00'),
  ('00000000-0000-4000-8000-000000000012', 'completed', 'water_supply', '{"issue_type":"leakage","location":"पुराना शहर"}', false, NULL, NULL, '2026-09-26 20:10:00+00', '2026-09-26 20:15:00+00'),
  ('00000000-0000-4000-8000-000000000013', 'completed', 'water_supply', '{"issue_type":"dirty_water","location":"नया इलाका","duration_days":3}', false, NULL, NULL, '2026-09-28 07:00:00+00', '2026-09-28 07:05:00+00'),
  ('00000000-0000-4000-8000-000000000014', 'completed', 'water_supply', '{"issue_type":"low_pressure","location":"Mahatma Gandhi ward","duration_days":15,"address_detail":"पुराने बस स्टैंड के पीछे"}', false, NULL, NULL, '2026-09-23 11:25:00+00', '2026-09-23 11:30:00+00'),
  ('00000000-0000-4000-8000-000000000015', 'completed', 'water_supply', '{"issue_type":"other","location":"रानी कमलापति","duration_days":2}', false, NULL, NULL, '2026-09-27 08:40:00+00', '2026-09-27 08:45:00+00')
ON CONFLICT (id) DO NOTHING;

-- Tickets. office_id resolved by (department, level, code) lookup, never a hardcoded id.

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000001', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '1'),
  'new', '{"issue_type":"no_supply","location":"वार्ड 1","duration_days":3,"address_detail":"वार्ड कार्यालय के पास"}',
  'Issue: No water supply; Location: वार्ड 1; Days affected: 3; Address or landmark: वार्ड कार्यालय के पास',
  '3 दिन से पानी नहीं आ रहा, वार्ड 1, वार्ड कार्यालय के पास', NULL, NULL, NULL, 0.95,
  '2026-09-28 08:10:00+00', '2026-09-28 08:10:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000001');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000002', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '1'),
  'in_progress', '{"issue_type":"leakage","location":"महात्मा गांधी वार्ड","duration_days":1}',
  'Issue: Pipe or tap leakage; Location: महात्मा गांधी वार्ड; Days affected: 1',
  'कल से पाइप लीक हो रहा है, महात्मा गांधी वार्ड में', NULL, NULL, NULL, 0.88,
  '2026-09-26 10:05:00+00', '2026-09-27 09:00:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000002');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000003', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '24'),
  'new', '{"issue_type":"low_pressure","location":"Habibganj","duration_days":5,"address_detail":"हबीबगंज स्टेशन के पास"}',
  'Issue: Low pressure; Location: Habibganj; Days affected: 5; Address or landmark: हबीबगंज स्टेशन के पास',
  '5 दिनों से पानी का दबाव बहुत कम है, Habibganj, स्टेशन के पास', NULL, NULL, NULL, 0.91,
  '2026-09-28 07:40:00+00', '2026-09-28 07:40:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000003');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000004', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '24'),
  'resolved', '{"issue_type":"dirty_water","duration_days":2}',
  'Issue: Dirty or smelly water; Location: 23.2493, 77.423; Days affected: 2',
  '2 दिन से पानी गंदा आ रहा है (लोकेशन साझा की)', NULL, 23.2493, 77.4230, 1.00,
  '2026-09-25 14:20:00+00', '2026-09-27 16:45:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000004');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000005', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '52'),
  'new', '{"issue_type":"no_supply","location":"मिसरोद","duration_days":7,"address_detail":"मिसरोद बस स्टैंड के पास"}',
  'Issue: No water supply; Location: मिसरोद; Days affected: 7; Address or landmark: मिसरोद बस स्टैंड के पास',
  'एक हफ्ते से पानी नहीं आ रहा, मिसरोद बस स्टैंड के पास', NULL, NULL, NULL, 0.93,
  '2026-09-28 06:55:00+00', '2026-09-28 06:55:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000005');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000006', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '52'),
  'in_progress', '{"issue_type":"other","location":"Misrod","address_detail":"टंकी के पास अजीब गंध"}',
  'Issue: Other water issue; Location: Misrod; Address or landmark: टंकी के पास अजीब गंध',
  'पानी की टंकी के पास अजीब गंध आ रही है, Misrod', NULL, NULL, NULL, 0.82,
  '2026-09-26 18:30:00+00', '2026-09-27 11:10:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000006');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000007', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '60'),
  'resolved', '{"issue_type":"leakage","location":"गोविंदपुरा","duration_days":2}',
  'Issue: Pipe or tap leakage; Location: गोविंदपुरा; Days affected: 2',
  '2 दिन से नल से पानी लीक हो रहा है, गोविंदपुरा', NULL, NULL, NULL, 0.90,
  '2026-09-24 09:00:00+00', '2026-09-26 12:00:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000007');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000008', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '60'),
  'new', '{"issue_type":"low_pressure","location":"Govindpura","duration_days":10,"address_detail":"गोविंदपुरा औद्योगिक क्षेत्र"}',
  'Issue: Low pressure; Location: Govindpura; Days affected: 10; Address or landmark: गोविंदपुरा औद्योगिक क्षेत्र',
  '10 दिनों से पानी का प्रेशर कम है, Govindpura औद्योगिक क्षेत्र', NULL, NULL, NULL, 0.87,
  '2026-09-28 09:20:00+00', '2026-09-28 09:20:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000008');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000009', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '80'),
  'in_progress', '{"issue_type":"dirty_water","location":"Kolar Road","duration_days":4,"address_detail":"कोलार रोड, सर्वधर्म कॉलोनी"}',
  'Issue: Dirty or smelly water; Location: Kolar Road; Days affected: 4; Address or landmark: कोलार रोड, सर्वधर्म कॉलोनी',
  '4 दिन से पानी गंदा आ रहा है, Kolar Road, सर्वधर्म कॉलोनी', NULL, NULL, NULL, 0.94,
  '2026-09-27 15:10:00+00', '2026-09-28 08:00:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000009');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000010', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '80'),
  'new', '{"issue_type":"no_supply","duration_days":1}',
  'Issue: No water supply; Location: 23.2156, 77.4384; Days affected: 1',
  'आज से पानी नहीं आ रहा (लोकेशन साझा की)', NULL, 23.2156, 77.4384, 1.00,
  '2026-09-28 10:05:00+00', '2026-09-28 10:05:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000010');

-- Fallback/needs_review tickets: confidence 0.00, matched_via = fallback (no ward name match >= 80,
-- and no GPS given) -- the only way S09's resolver actually produces needs_review (S10 D-S10-3).

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000011', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'district' AND code = 'BMC-HQ'),
  'needs_review', '{"issue_type":"no_supply","location":"नयापुरा","duration_days":6}',
  'Issue: No water supply; Location: नयापुरा; Days affected: 6',
  '6 दिन से पानी नहीं आ रहा, नयापुरा इलाका', NULL, NULL, NULL, 0.00,
  '2026-09-27 12:00:00+00', '2026-09-27 12:00:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000011');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000012', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'district' AND code = 'BMC-HQ'),
  'needs_review', '{"issue_type":"leakage","location":"पुराना शहर"}',
  'Issue: Pipe or tap leakage; Location: पुराना शहर',
  'पाइप लीक हो रहा है, पुराना शहर के आसपास', NULL, NULL, NULL, 0.00,
  '2026-09-26 20:15:00+00', '2026-09-26 20:15:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000012');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000013', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'district' AND code = 'BMC-HQ'),
  'needs_review', '{"issue_type":"dirty_water","location":"नया इलाका","duration_days":3}',
  'Issue: Dirty or smelly water; Location: नया इलाका; Days affected: 3',
  '3 दिन से पानी गंदा आ रहा है, नया इलाका में', NULL, NULL, NULL, 0.00,
  '2026-09-28 07:05:00+00', '2026-09-28 07:05:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000013');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000014', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '1'),
  'resolved', '{"issue_type":"low_pressure","location":"Mahatma Gandhi ward","duration_days":15,"address_detail":"पुराने बस स्टैंड के पीछे"}',
  'Issue: Low pressure; Location: Mahatma Gandhi ward; Days affected: 15; Address or landmark: पुराने बस स्टैंड के पीछे',
  '15 दिनों से पानी का दबाव कम है, Mahatma Gandhi ward, पुराने बस स्टैंड के पीछे', NULL, NULL, NULL, 0.89,
  '2026-09-23 11:30:00+00', '2026-09-25 09:50:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000014');

INSERT INTO tickets (session_id, service_id, department, office_id, status, fields, summary_en, original_text, audio_path, lat, lng, routing_confidence, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000015', 'water_supply', 'Jal Vibhag',
  (SELECT id FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward' AND code = '24'),
  'in_progress', '{"issue_type":"other","location":"रानी कमलापति","duration_days":2}',
  'Issue: Other water issue; Location: रानी कमलापति; Days affected: 2',
  'पानी से जुड़ी अन्य समस्या है, रानी कमलापति वार्ड में, 2 दिन से', NULL, NULL, NULL, 0.85,
  '2026-09-27 08:45:00+00', '2026-09-27 19:20:00+00'
WHERE NOT EXISTS (SELECT 1 FROM tickets WHERE session_id = '00000000-0000-4000-8000-000000000015');
