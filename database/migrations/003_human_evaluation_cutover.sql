-- 003 -- cutover: General Triage becomes Human Evaluation for EXISTING data. Run when the new code is deployed (after migration 002), NOT before:
-- the previous code still creates tickets for the department 'General Triage' and needs its office. Existing tickets keep their ids and history.
-- Safe to re-run.
DO $$
DECLARE old_id bigint; new_id bigint;
BEGIN
  SELECT id INTO old_id FROM offices WHERE department = 'General Triage'   AND level = 'district' ORDER BY id LIMIT 1;
  SELECT id INTO new_id FROM offices WHERE department = 'Human Evaluation' AND level = 'district' ORDER BY id LIMIT 1;
  IF old_id IS NOT NULL AND new_id IS NULL THEN  -- 002 not applied: just rename the desk
    UPDATE offices SET department = 'Human Evaluation', code = 'HE-HQ', office_name = 'Human Evaluation Desk (DEMO)' WHERE id = old_id;
  ELSIF old_id IS NOT NULL AND new_id IS NOT NULL THEN  -- move the tickets to the new desk and retire the old one
    UPDATE tickets SET office_id = new_id WHERE office_id = old_id;
    UPDATE offices SET active = false WHERE id = old_id;
  END IF;
END $$;
UPDATE tickets SET department = 'Human Evaluation', service_id = 'human_evaluation' WHERE department = 'General Triage' OR service_id = 'general';
