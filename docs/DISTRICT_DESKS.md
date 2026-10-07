# District desks: who a complaint goes to, in every district

Written 2026-10-08. Generated table below; the rest is by hand. Source of the decisions: `specs/registry/district_desks.yaml`. The migration: `database/migrations/007_district_desks.sql`
(made by `backend/scripts/gen_district_desks.py`; edit the yaml and run the script again, never the SQL).

## What this is
Until now every office in the database was a Bhopal office, so a complaint from any other district was sent to Bhopal and marked "needs review". A **desk** is one office row: a department, a district and the
name of the office that handles that department there (for example "Chief Medical and Health Officer (CMHO), Rajgarh"). With a desk in the citizen's district the ticket goes straight to it, as "new".

- **38 departments** have a desk in each of the 55 districts (2,090 desks). The district comes from what the citizen says, or from their shared GPS location (see below).
- **11 departments** work from the state capital only, so they have one state desk each (for example the Directorate of Medical Education, Bhopal). Every complaint for them goes there, as "new".
- A desk is a **designation, not a person**: the complaint stays on the desk when the officer is transferred, and the CM office changes who holds the key from the dashboard (`docs/specs/S40-desk-access.md`). No officer names, phone numbers or emails are stored. The officer dashboards need a place to send the complaint; the citizen's own phone number is what the officer uses to call back.

## Where the designations come from (public sources)
The officer directories of the district portals (`<district>.nic.in`, "Who's who" or "District officers directory"), downloaded on 2026-10-08.
- 45 of the 55 districts publish a directory. 13 are detailed (40 to 440 rows); 32 are a short "Who's who" (Collector, SDMs, CEO and a few more).
- No directory exists online for: Anuppur, Ashoknagar, Chhatarpur, Niwari, Sagar, Sehore, Seoni, Shahdol, Sheopur, Tikamgarh.
- Where the directories are short or silent, the department's own standard structure is used and the `confidence` column says so.
- The last two columns count how many of the 13 detailed and of all 45 directories list a matching office. A low number mostly means the directory is short, not that the office is missing.

## How good is it
- **high**: the office is listed in most of the detailed directories (for example Zila Panchayat CEO 12 of 13, Superintendent of Police 11 of 13, CMHO 9 of 13).
- **medium**: listed in some and standard for the department. A few districts share an office (a PWD division or a DISCOM circle can cover two districts, forest divisions follow forests not districts).
- **low**: no district office was found; the state desk is used. These are exactly the ones to confirm with the department.
- Not checked against each department's own order or website. Before real use, send each department the line for its desk and ask them to confirm the designation, and to give the officer and the contact.

## Choosing the district from a shared GPS location
If the citizen shares their location, the district is worked out from it (`app/district_geo.py`, boundaries in `specs/registry/district_geo.json` from OpenStreetMap contributors, ODbL).
Tested on 18 known places inside Madhya Pradesh (all 55 districts have a boundary, including Maihar, Mauganj, Pandhurna, Niwari and Agar Malwa) and 3 outside the state (correctly none).
The boundaries are simplified to about 2 km: a point very close to a border can land in the neighbouring district. A district the citizen types themselves always wins.

## Not done yet
- Block / tehsil offices (Janpad Panchayat, Block Education Officer, Tehsildar): needs the LGD block list and the block structure of each department.
- Departments with district desks only in some districts (government medical colleges, jails): they use the state desk until the list of districts is confirmed.
- Officer names, phone numbers and emails per desk.
- Running the migration on the live database (migrations 004, 005 and then 007, in that order).

<!-- table:start -->
| Department | Scope | Desk | Confidence | Seen in detailed / all directories |
|---|---|---|---|---|
| AYUSH Department | district | District AYUSH Officer | medium | 2/13 · 2/45 |
| Anand Department | state | Anand Department (Anand Sansthan), Bhopal | low | 0/13 · 0/45 |
| Animal Husbandry Department | district | Deputy Director, Veterinary Services | high | 6/13 · 7/45 |
| Backward Classes and Minority Welfare Department | district | District Officer, Backward Classes and Minority Welfare | medium | 4/13 · 4/45 |
| Bijli Vibhag | district | Superintending Engineer, Electricity Distribution (DISCOM) | medium | 2/13 · 2/45 |
| Civil Aviation Department | state | Directorate of Civil Aviation, Bhopal | medium | 1/13 · 1/45 |
| Commercial Tax Department | district | Commercial Tax Officer | medium | 4/13 · 4/45 |
| Cooperative Department | district | Deputy Commissioner / Deputy Registrar, Cooperative Societies | medium | 4/13 · 4/45 |
| Cottage and Village Industries Department | district | District Khadi and Village Industries Office | medium | 4/13 · 4/45 |
| Culture Department | state | Directorate of Culture, Bhopal | low | 0/13 · 0/45 |
| Farmer Welfare and Agriculture Department | district | Deputy Director, Farmer Welfare and Agriculture Development | high | 6/13 · 7/45 |
| Finance Department and Treasury | district | District Treasury Officer | high | 9/13 · 13/45 |
| Fisheries Department | district | Assistant Director, Fisheries | medium | 4/13 · 5/45 |
| Food Civil Supplies Department | district | District Supply Officer | high | 5/13 · 7/45 |
| Food and Drug Administration | district | District Food Safety Officer / Drug Inspector | medium | 3/13 · 3/45 |
| Forest Department | district | Divisional Forest Officer | high | 8/13 · 17/45 |
| General Administration Department | district | Collector Office | high | 12/13 · 44/45 |
| Higher Education Department | state | Commissioner, Higher Education, Bhopal | medium | 4/13 · 5/45 |
| Home Department (Police) | district | Superintendent of Police Office | high | 11/13 · 35/45 |
| Horticulture and Food Processing Department | district | Deputy / Assistant Director, Horticulture | high | 7/13 · 8/45 |
| Industrial Policy and Investment Department | district | General Manager, District Trade and Industry Centre | high | 4/13 · 5/45 |
| Jail Department | state | Director General, Prisons, Bhopal | medium | 4/13 · 4/45 |
| Jal Vibhag | district | Executive Engineer, Public Health Engineering | high | 7/13 · 9/45 |
| Labour Department | district | District Labour Officer | medium | 4/13 · 6/45 |
| Law and Legislative Affairs Department | state | Law and Legislative Affairs Department, Bhopal | medium | 2/13 · 2/45 |
| Lok Nirman Vibhag | district | Executive Engineer, Public Works Department | high | 10/13 · 12/45 |
| MSME Department | district | General Manager, District Trade and Industry Centre | high | 4/13 · 5/45 |
| Medical Education Department | state | Directorate of Medical Education, Bhopal | medium | 3/13 · 3/45 |
| Mineral Resources Department | district | District Mining Officer | high | 6/13 · 7/45 |
| Nagar Nigam Sanitation | district | Municipal body of the district headquarters (Chief Municipal Officer / Commissioner) | medium | 9/13 · 12/45 |
| Narmada Valley Development Department | state | Narmada Valley Development Authority, Bhopal | medium | 2/13 · 3/45 |
| New and Renewable Energy Department | district | District Renewable Energy Officer | medium | 3/13 · 3/45 |
| Panchayat and Rural Development Department | district | Zila Panchayat CEO Office | high | 12/13 · 38/45 |
| Planning Economics and Statistics Department | district | District Planning Officer | high | 5/13 · 5/45 |
| Public Health and Family Welfare Department | district | Chief Medical and Health Officer (CMHO) | high | 9/13 · 10/45 |
| Public Relations Department | district | District Public Relations Officer | high | 7/13 · 10/45 |
| Public Service Commission | state | MPPSC Office, Indore | high | 1/13 · 1/45 |
| Public Service Management Department | district | District Manager, Public Service Management (Lok Seva) | high | 4/13 · 5/45 |
| Revenue Department | district | Collectorate (Revenue) | high | 12/13 · 44/45 |
| Scheduled Caste Welfare Department | district | Assistant Commissioner, Tribal and Scheduled Caste Welfare | medium | 8/13 · 8/45 |
| School Education Department | district | District Education Officer | high | 7/13 · 8/45 |
| Science and Technology Department | state | Department of Science and Technology (MPCST), Bhopal | low | 0/13 · 0/45 |
| Social Justice and Disability Welfare Department | district | District Social Justice Office (Deputy Director) | medium | 4/13 · 7/45 |
| State Election Commission and Electoral Roll | district | District Election Officer (Collector) Office | high | 12/13 · 44/45 |
| Technical Education Skill and Employment Department | district | District Employment Officer | medium | 4/13 · 5/45 |
| Tourism Department | state | Madhya Pradesh Tourism Board, Bhopal | medium | 2/13 · 2/45 |
| Transport Department | district | Regional / District Transport Office (RTO / DTO) | high | 6/13 · 7/45 |
| Tribal Affairs Department | district | Assistant Commissioner, Tribal Welfare (District Coordinator) | high | 8/13 · 8/45 |
| Women and Child Development Department | district | District Programme Officer, Women and Child Development | high | 8/13 · 10/45 |
<!-- table:end -->
