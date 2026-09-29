# Department structure and a central way to manage it (architecture, 30 Sep 2026)

Status: **proposal + reference**. Nothing in this file is implemented; it records what the research found, how departments are wired today,
and a simple design that puts all department/office data in one reviewable place. Sources: `docs/research/T05-research.md`,
`docs/specs/S02`, `S03`, `S09`, `S10`, `S28`, the `specs/*.yaml` files and `database/*.sql`. Rule carried over from S09: **never invent official
data**; every value has a source or is marked demo/unverified.

## 1. What the research says a department looks like (Bhopal, T05 research, checked 27 Sep)
```
State department (e.g. PHED, PWD)  --- district / regional offices
Bhopal Municipal Corporation (BMC), overseen by the Municipal Commissioner
   |-- wings: water supply, public works, sanitation/health, revenue/tax, planning, fire, finance
   |-- ZONES (19 or 21, sources disagree)  ->  WARDS (85 or 86, sources disagree)
   |-- head office: Harshwardhan Complex, Mata Mandir, Bhopal 462001 (verified, official)
Citizen channels: CM Helpline, toll-free, email, WhatsApp, BMC portal (a complaint needs a zone/ward number)
```
| Fact | Status |
|---|---|
| BMC head office and contact | **Verified** (official `.nic.in` page) |
| BMC wings (water, works, sanitation, ...) | Secondary source, medium confidence |
| Ward count 85 vs 86, current ward names | **Unverified** (non-official OpenCity dataset) |
| Zone to ward mapping, zone count | **NOT FOUND** |
| Ward centres (lat/lng) | **NOT FOUND** (boundary polygons exist, no points) |
| Officer names and roles per zone | **NOT FOUND** |
| Who owns a "no water" complaint | **Ambiguous**: BMC distribution vs PHED (Kolar plant, bulk supply) |
| MPOnline's own Customer Solutions Hub | Has "department-wise issues" dashboards; no public detail on routing |

Consequence: the real hierarchy is **department -> body -> zone -> ward**, but only the top and the head office are verified. Our data model
must carry that shape without pretending the lower levels are known.

## 2. How a department is wired today (as built)
| Piece | Where it lives | Problem |
|---|---|---|
| Department **name** | a plain text line in each `specs/<service>.yaml` (`department: Bijli Vibhag`) | a string, repeated, no id |
| Department **offices** | rows in `offices` (`department`, `level`, `code`, `name`, `aliases`, centroid, `office_name`, `officer_name`, `active`); data in `database/seed.sql` and `seed_departments.sql`, some also inserted through the API | two SQL files plus manual inserts; no single reviewed source |
| Department on a **ticket** | `tickets.department` (text copy, changed by cross-department reassign) | text join, typo-prone |
| **Labels** for the dashboard | hardcoded in `dashboard/src/dashboard/labels.py` | must be edited by hand per department |
| **Questions/fields** | the same spec YAML | fine: this is the service definition |
| Demo vs verified | comments in SQL / `(DEMO)` in office names | not machine-readable |
The link between them is the department **string**. It works, but adding a department means touching four places and nothing checks they agree.

## 3. Proposed design: one registry file as the source of truth
```
registry/departments.yaml         <- the ONLY place a human edits department and office data (reviewed in git)
        |  validate  (tests + `python -m registry check`)
        v
  sync tool (idempotent upsert)  ---->  Supabase `offices`  (runtime store, unchanged schema)
        |
        +---->  dashboard labels, ward lists, department filter  (read from specs + registry, nothing hardcoded)
        +---->  service specs reference a department by ID, not by free text
```
### 3.1 Registry shape (illustrative)
```yaml
departments:
  - id: water_supply            # stable id, same as the service spec id
    name: {en: Jal Vibhag, hi: जल विभाग}
    body: Bhopal Municipal Corporation      # who runs it (T05: BMC vs PHED is ambiguous, note it)
    verified: false            # false = demo or unverified; true only with a source
    source: null               # URL or document when verified
    offices:
      - {level: district, code: BMC-HQ, name: Bhopal, office_name: BMC Head Office, verified: true,
         source: "https://bhopal.nic.in/en/public-utility/bhopal-municipal-corporation/"}
      - {level: ward, code: "52", name: मिसरोद, aliases: [Misrod], office_name: "Ward मिसरोद Office", verified: false}
```
### 3.2 Rules the validator enforces (run in tests and before every sync)
1. Every service spec's `department` matches a registry department (no orphan spec, no orphan department).
2. Every department has **exactly one active `district` office** (the routing fallback; S02, S09).
3. `(department, level, code)` is unique; ward `aliases` do not collide within a department (would cause tied fuzzy matches).
4. Anything without a `source` must carry `verified: false`; the sync writes `(DEMO)`/unverified markers so officers can see them.
5. No placeholder officer names: `officer_name` stays empty until verified (S09).
6. Levels come from the S01 `OfficeLevel` list.

### 3.3 Everyday tasks
| Task | Steps |
|---|---|
| Add a department | add `specs/<id>.yaml` (fields, questions) + a registry entry with a district office + `sync` |
| Add or fix a ward / office | edit the registry, open the diff for review, `sync` |
| Mark data verified | add its `source`, set `verified: true`, review, `sync` |
| Retire an office | `active: false` (never delete: tickets point at it) |
| Reassign a wrong ticket | dashboard, as today (cross-department, logged in `routing_corrections`) |

### 3.4 Phasing
| Phase | What | Schema change | When |
|---|---|---|---|
| **A: registry + sync + checks** | the file, the validator, the sync tool, dashboard labels read from it | none | first thing after submission (keeps the freeze safe) |
| **B: `departments` table** | id, names, body, verified, source; FK from `offices` and `tickets` (replaces the text join) | migration | when the pilot grows past demo |
| **C: admin tab on the dashboard** | edit offices with an audit log, still writing the same tables | none | after B, with officer accounts (needs per-department access, PROJECT.md §11) |
| **D: real hierarchy** | `body -> zone -> ward` parent links, real centroids from the ward boundary file, LGD codes | migration | once BMC zone/ward data is obtained and verified |

## 4. Why this is "easy but central"
- **One file to edit**, in git, so every change to who-handles-what is reviewed and traceable (this is also the audit trail for judges).
- **No schema change** to start, so it is safe to do right after the freeze.
- **The database stays the runtime store**; the registry is the reviewed source, and the sync is repeatable.
- **Honest by construction**: the `verified`/`source` fields make the demo-vs-real difference machine-readable, instead of living in comments.
- **Grows into the real shape** (body -> zone -> ward) without rewriting anything.

## 5. Open questions (need the team, not more code)
1. Ward count 85 or 86, and is the OpenCity ward list acceptable for the pilot? (T05 question 1)
2. Do we need real zone data, or is a flat ward list enough for the pilot? (T05 question 2)
3. Which body owns which complaint type in practice (BMC vs PHED for water)? Someone should ask BMC, not a search engine.
4. Who is the owner of the registry after the event (Lead, Dev, or a department nodal officer)?

## 6. Current gaps to remember (not part of this design)
Demo offices for electricity, roads, sanitation and general triage are constructed for the demo and flagged `(DEMO)`; centroids are empty, so
GPS never picks a ward; there is no per-department login and no push notification to an officer.
