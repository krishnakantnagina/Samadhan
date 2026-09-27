# Plan: T05 — Pilot jurisdiction data (`database/seed.sql`)

Ticket: `docs/TICKETS.md` T05. Spec: `docs/specs/S09-jurisdiction.md` §PILOT DATA + §ACCEPTANCE
(T05 half). Depends on T03 (`database/schema.sql` must exist and have run — see
`docs/plans/T06-plan.md` §T03, which comes first in build order).

## Exact rows

6 rows into `offices`, all `department = 'Jal Vibhag'`. `id` is left to the identity column.
Column-by-column status (S09's rule: never invent — every DEMO/NOT FOUND stays visible here, not
just in S09).

| level | code | name (hi) | aliases | centroid_lat/lng | office_name | officer_name |
|---|---|---|---|---|---|---|
| ward | `1` (DEMO) | महात्मा गांधी (DEMO) | Mahatma Gandhi (DEMO) | NULL (NOT FOUND) | "Ward महात्मा गांधी Office" (DEMO) | NULL (NOT FOUND) |
| ward | `24` (DEMO) | रानी कमलापति (DEMO) | Rani Kamlapati, Habibganj (DEMO — both from T05 research §3) | NULL (NOT FOUND) | "Ward रानी कमलापति Office" (DEMO) | NULL (NOT FOUND) |
| ward | `52` (DEMO) | मिसरोद (DEMO) | Misrod (DEMO) | NULL (NOT FOUND) | "Ward मिसरोद Office" (DEMO) | NULL (NOT FOUND) |
| ward | `60` (DEMO) | गोविंदपुरा (DEMO) | Govindpura (DEMO) | NULL (NOT FOUND) | "Ward गोविंदपुरा Office" (DEMO) | NULL (NOT FOUND) |
| ward | `80` (DEMO) | सर्वधर्म कोलार (DEMO) | Sarvadharm Kolar, Kolar Road (DEMO) | NULL (NOT FOUND) | "Ward सर्वधर्म कोलार Office" (DEMO) | NULL (NOT FOUND) |
| district | `BMC-HQ` (DEMO — assigned code, not sourced) | Bhopal (**VERIFIED** — district name) | BMC, Bhopal Municipal Corporation, Bhopal Nagar Nigam (**VERIFIED**, bhopal.nic.in) | NULL (NOT FOUND) | "BMC Head Office" (DEMO label; underlying org/address is VERIFIED — see note) | NULL (NOT FOUND) |

**Note:** S02's `offices` table has no address/phone/email column, so the VERIFIED contact
(Harshwardhan Complex, Mata Mandir, Bhopal 462001) isn't stored anywhere — S01's `ticket.office`
only ever returns `{name, level}`, so nothing downstream needs it. Not a gap, just worth knowing.

## `database/seed.sql`

```sql
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
```

## Verification SQL + expected results

Run after `schema.sql` + this file, and again after a second run of this file alone (idempotency
check).

```sql
SELECT count(*) FROM offices WHERE department = 'Jal Vibhag' AND level = 'ward';
-- expected: 5

SELECT count(*) FROM offices WHERE department = 'Jal Vibhag' AND level = 'district' AND active;
-- expected: 1  (S02: exactly one active district row per department)

SELECT code, name, office_name FROM offices WHERE department = 'Jal Vibhag' ORDER BY level, code;
-- expected: the 6 rows above, in this order (district row last, code 'BMC-HQ')

SELECT count(*) FROM offices WHERE department = 'Jal Vibhag';
-- run seed.sql a second time, then re-run this query
-- expected: still 6 (ON CONFLICT DO NOTHING — no duplicates)
```

## Mapping to S09 T05 acceptance

| S09 T05 acceptance item | Satisfied by |
|---|---|
| 5 ward rows + 1 district row for `department = Jal Vibhag` | The 6-row `INSERT` above |
| `unique(department, level, code)` holds | Relies on T03's `schema.sql` constraint (S02); `ON CONFLICT` targets it directly |
| Exactly one active `district` row | Only one `district`-level row in the `INSERT`; verification query 2 |
| Every DEMO value labeled as such | Column table above + inline SQL comment pointing back here |
