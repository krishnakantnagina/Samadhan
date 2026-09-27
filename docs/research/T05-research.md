# T05 Research — Pilot Office Data (Bhopal, `water_supply`)

Research only. No seed data, SQL, or YAML written from this. Tool: web search/fetch, checked 27 Sep 2026.
Rule followed throughout: no invented ward names, codes, coordinates, offices, or people — gaps are marked `NOT FOUND`, never filled with a plausible guess.

## Headline finding

**Reliable, current, official structure data for Bhopal's zones/wards/water offices is not available through web search.** What's confirmed from an official (`.nic.in`) source is limited to BMC's existence and head-office contact details. Ward names for the *current* (2024) delimitation come only from a non-official geodata aggregator. No current official zone→ward mapping, no officer-role list, and no ward centroid coordinates were found. This needs an RTI request or a direct visit to `bmconline.gov.in`'s citizen-services section (its main portal is a JS-rendered SAP app that doesn't expose content to a page fetch) before T05 can be built on solid ground.

## 1. Who handles municipal water-supply complaints in Bhopal

| Fact | Source | Date checked | Confidence |
|---|---|---|---|
| Bhopal Municipal Corporation (BMC) / "Bhopal Nagar Nigam" is the civic body for Bhopal city; its head office is at Harshwardhan Complex, Mata Mandir, Bhopal (M.P.) 462001, phone +91-755-2701222, email commoffice@bmconline.gov.in | [bhopal.nic.in — Bhopal Municipal Corporation](https://bhopal.nic.in/en/public-utility/bhopal-municipal-corporation/) (official `.nic.in` district site) | 27 Sep 2026 | **High** — official source |
| BMC's official online portal is `bmconline.gov.in` (SAP-based citizen services) | Same page, plus [bmconline.gov.in](https://www.bmconline.gov.in/sap/bc/ui5_ui5/sap/zbmcprdhome/index.html) | 27 Sep 2026 | High (URL confirmed), but the portal itself is a JavaScript SAP UI5 app — fetching it returns only a bare "App Title" shell, no content. Anyone continuing this research needs a real browser, not a fetch, to get past this page. |
| Citizens can lodge civic complaints (water, road, sewerage, streetlight) to BMC via the CM Helpline (`cmhelpline.mp.gov.in`), a toll-free number, email, WhatsApp, or the BMC portal; a complaint needs a zone/ward number | [complainthub.org — BMC Bhopal complaint guide](https://complainthub.org/bmc-bhopal/) | 27 Sep 2026 | **Medium** — non-official citizen-help aggregator, not BMC/government itself. Consistent with T09/PROJECT.md's own reference to the CM Helpline as evidence, so plausible, but not independently confirmed on an official page. |
| BMC's water department is sometimes called "Jal Karya Vibhag" / water works wing | An earlier AI-search synthesis surfaced this term, but the actual source page it cited (`jsv.hp.nic.in`) is **Himachal Pradesh's** Jal Shakti Vibhag — a different state, not Bhopal or MP. | 27 Sep 2026 | **Not verified — likely wrong.** Do not use "Jal Karya Vibhag" as Bhopal's official department name without a Bhopal/MP-specific source. `specs/water_supply.yaml`'s `department: "Jal Vibhag"` (matching `mock/app.py`'s `DEPARTMENT = "Jal Vibhag"`) was **not** confirmed or contradicted by anything found — it's a plausible generic Hindi term for "water department" but I found no BMC page using it verbatim. |
| BMC's water supply is a Municipal Commissioner-overseen department, one of several (public works, revenue/tax, water supply, planning, fire, health/sanitation, finance) | [Wikipedia — Bhopal Municipal Corporation](https://en.wikipedia.org/wiki/Bhopal_Municipal_Corporation) | 27 Sep 2026 | **Low-medium** — Wikipedia, not official; consistent with how Indian municipal corporations are generally structured, but no BMC-specific org chart page was found to confirm a distinct "water supply department" name or head. |

## 2. Zones and wards

| Fact | Source | Date checked | Confidence |
|---|---|---|---|
| Bhopal Municipal Corporation is divided into **85 or 86 wards** depending on the delimitation cited. A 2024 delimitation is referenced by multiple non-official sources. | [Wikipedia](https://en.wikipedia.org/wiki/Bhopal_Municipal_Corporation) (85, citing civicatlas.in) vs. [bharatlas.com](https://bharatlas.com/view/wards_bhopal) (86, citing OpenCity/Esri India Living Atlas, dataset snapshot 26 May 2026) vs. [data.opencity.in dataset](https://data.opencity.in/dataset/bhopal-wards-map/resource/9b8325e9-44ec-448b-890c-1c19f312d06b) ("Wards map ... from 2024 with 85 wards", KML, updated 25 Nov 2025) | 27 Sep 2026 | **UNVERIFIED, conflicting.** No official BMC/MP gazette page was reachable to resolve 85 vs. 86. |
| An older, superseded delimitation fixed **85 wards** by a Madhya Pradesh gazette notification (under the MP Municipal Corporation Act, 1956), No. 449, dated 24 Sep 2014 | [indianemployees.com gazette republication](https://www.indianemployees.com/gazette-notifications/details/fixation-of-boundaries-of-85-wards-of-municipal-corporation-bhopal) — republishes the notification number/date/subject but not the actual ward list (linked PDF wasn't retrievable) | 27 Sep 2026 | **Medium** — this is a real 2014 notification, but it is 10+ years old and pre-dates the "2024 delimitation" mentioned elsewhere; **not the current ward map**, listed for context only. |
| Current (2024-delimitation) ward **names**, numbered 1–85 (ward 86's name wasn't returned by the fetch), in Hindi | [bharatlas.com ward map](https://bharatlas.com/view/wards_bhopal), sourced from OpenCity.in / Esri India Living Atlas | 27 Sep 2026 | **UNVERIFIED — non-official aggregator.** Internally consistent with Wikipedia's English ward names for the numbers that overlap (checked wards 1, 7, 15), which is a good sign, but neither source is BMC/government itself. |
| Zone→ward groupings for the *current* delimitation | Searched specifically; not found. | 27 Sep 2026 | **NOT FOUND.** The only zone→ward list found (Slideshare, "Bhopal Nagar Nigam zone wise ward no list") covers only wards 1–70 across 14 zones and cites `bhopalmunicipal.com/zoneoffice.htm` (a defunct/pre-rebrand domain) and `onlinetps.com` — clearly a much older delimitation, **not usable for the current pilot.** |
| Total zone count today | Two non-official secondary sources disagree: "19 zones" ([cseindia.org waste-data page](https://www.cseindia.org/bhopal-municipal-corporation-8283), a sentence with no citation of its own) vs. "21 zones" ([complainthub.org](https://complainthub.org/bmc-bhopal/), also uncited) | 27 Sep 2026 | **UNVERIFIED, conflicting, both uncited.** Possibly both ultimately copy one another or a third uncited source — treat as unverified until an official count is found. |
| A 1984 ward list exists on an MP government subdomain (`bgtrrdmp.mp.gov.in`, the Bhopal Gas Tragedy Relief & Rehabilitation Dept.) | [bgtrrdmp.mp.gov.in](https://www.bgtrrdmp.mp.gov.in/MUNICIPAL%20WARD%20AND%20CODES%20USED%20IN%20TISS%20SUMMARY.html) | 27 Sep 2026 | Official domain, but the content is explicitly dated "3rd December 1984" and used for gas-tragedy survey purposes — **irrelevant to current wards/zones**, noted only so nobody else re-finds and misuses it. |

## 3. Five wards picked for the pilot

Because no current, verified zone→ward mapping exists (see §2), wards below are **not** picked "spread across zones" as the ticket asks — that can't be done responsibly yet. They're picked instead to be geographically and characterwise distinct, using well-known Bhopal locality names that appear in the (unverified) current ward list, so the pilot at least covers different *kinds* of area:

| Ward # | Name (from the unverified 2024 ward list) | Why picked |
|---|---|---|
| 1 | महात्मा गांधी (Mahatma Gandhi) | Old-city/central ward — same general area as BMC's own head office address (Mata Mandir) |
| 24 | रानी कमलापति (Rani Kamlapati) | Named for the area around Rani Kamlapati (Habibganj) station — a newer, redeveloped commercial/transit hub, distinct character from ward 1 |
| 52 | मिसरोद (Misrod) | Well-known outer southeastern growth-corridor suburb |
| 60 | गोविंदपुरा (Govindpura) | Well-known eastern industrial-area locality |
| 80 | सर्वधर्म कोलार (Sarvadharm Kolar) | Well-known southwestern outer suburb along Kolar Road |

**This selection is UNVERIFIED and provisional.** It should be re-checked once (a) the 85-vs-86 ward count is resolved and (b) an actual zone map exists, since "spread across zones" was the actual instruction and can't be honoured without one.

## 4. Ward centres (lat/lng)

**NOT FOUND for all 5 wards.** No source returned point coordinates — only ward *boundary polygons* (the OpenCity/bharatlas KML/GeoJSON dataset referenced in §2). A centroid could be computed from that boundary file, but that requires downloading and parsing the KML with a GIS/geometry tool, which wasn't done here (out of scope for a search/fetch research pass, and not something to eyeball or estimate). **Concrete next step, not a guess:** download the dataset at `data.opencity.in/dataset/bhopal-wards-map` and compute each of the 5 wards' polygon centroid programmatically before T05 is built — do not hand-pick a coordinate off a map image.

## 5. Water-supply office/officer role per zone

**NOT FOUND.** No page gives current zone-level office/role titles for BMC water works (e.g. "Assistant Engineer, Water Works, Zone N"). One promising-looking search result turned out to be for a *different city's* corporation (Mumbai/MCGM's Section 4 RTI manuals for "Assistant Engineer Water Works" per ward) — noted here explicitly so it isn't mistaken for Bhopal data by anyone re-running this search. Recommended path: an RTI request to BMC's Public Information Officer (address on file: 2nd Floor, A Wing, ISBT Campus, Dr. Ambedkar Marg, Bhopal 462023, per [rtiguru.com](https://rtiguru.com/how-to-file-rti-in-bhopal-municipal-corporation-in-madhya-pradesh) — non-official RTI-filing guide site, address itself unverified against a primary source).

## 6. Fallback (district-level) office

| Fact | Source | Confidence |
|---|---|---|
| BMC's head/commissioner office — Harshwardhan Complex, Mata Mandir, Bhopal 462001; phone +91-755-2701222; email commoffice@bmconline.gov.in | [bhopal.nic.in](https://bhopal.nic.in/en/public-utility/bhopal-municipal-corporation/) | **High — official, verified** |

This is the strongest candidate for the S02 `offices` table's single active `district`-level row for the `water_supply` department (`level = "district"`, one per department per S02) — it's BMC's own head office, reachable when no ward match is found. Officer name is not applicable per the "roles only" rule and wasn't looked for.

## 7. What makes water routing ambiguous

| Fact | Source | Confidence |
|---|---|---|
| Roughly 60% of Bhopal's treated water comes from the Kolar Water Treatment Plant, which draws from Kolar Dam and is **managed by Madhya Pradesh's Public Health Engineering Department (PHED)**, not BMC directly | [thewaterdigest.com](https://thewaterdigest.com/bmc-readies-to-boost-water-supply-as-summer-peaks/) | **Medium** — trade-press site, not official, but a specific and checkable claim (plant name, %, agency) |
| The rest comes from Narmada River (via the Narmada Water Supply Scheme) and Bhopal's Upper Lake; Narmada-scheme infrastructure, once built by state-level bodies, is **handed over to BMC for O&M** | [bhopal.net](https://www.bhopal.net/bhopal-gets-narmada-water-but-no-word-of-water-for-poison-victims/) (an activist/NGO site — flagged clearly as non-official and possibly not neutral) | **Low-medium** — plausible and consistent with how NVDA-built schemes are usually handed off in MP, but this specific source has an advocacy angle and should not be treated as authoritative |
| Net effect for this project: **a citizen's "no water" complaint could technically be a BMC distribution problem or a PHED treatment/bulk-supply problem**, and the citizen has no way to know which. For M1 (routing everything to BMC's ward/district office regardless) this is fine, but it's worth the team knowing BMC may not always be the party that can actually fix it. | — | — |

No overlap with any other city's water body was found; nothing suggests a private contractor handles retail water complaints in Bhopal (no evidence found either way — not searched exhaustively).

## Questions for the team

1. Is 85 or 86 the current ward count, and is there an official (BMC/MP gazette) source for the 2024 delimitation, or do we accept the non-official OpenCity dataset as good enough for a hackathon pilot?
2. Do we need real zone→ward and officer-role data at all for the MVP, or is a single flat list of 5 ward names + one district fallback (no zone grouping) enough, given S02's `offices` table only requires `level` (`ward`/`district`), not a zone column?
3. Should someone actually open `bmconline.gov.in` in a browser (not a fetch) to check for a citizen-facing zone/ward directory that a JS-rendered page hid from this research pass?
4. Is an RTI request worth filing for officer-role titles, or is "Ward Office, Ward `<name>`" / "BMC Head Office" enough as the `office_name` for the pilot (no need for a role title at all)?
5. Who will download the OpenCity KML/GeoJSON and compute the 5 ward centroids — Lead or Dev — and is that even needed for M1 if the location field mostly comes from a citizen-typed place name plus GPS-to-nearest-known-point rather than true ward-polygon matching?

## What conflicts with S02, if anything

- S02's `offices` table has no `zone` column — only `level`, `code`, `name`, `aliases`, `centroid_lat/lng`, `office_name`, `officer_name`. This research couldn't find current zone data anyway, so **no conflict in practice**: S02 doesn't require zone data, and none is available to plug in even if it did.
- S02 requires `centroid_lat`/`centroid_lng` (nullable) for nearest-ward GPS matching (per PROJECT.md §4's "GPS → nearest ward centroid"). §4 of this research found **no coordinates at all**, only boundary polygons. If centroids aren't computed from the KML before T05/T06, GPS-based jurisdiction resolution (T16) has nothing to match against for the pilot wards — worth flagging to Dev before T16 starts, not just Lead.
- S02 requires "Exactly one active `district` row per department." §6 gives one clean, officially-sourced candidate (BMC head office) — no conflict, this one's solid.
- Everything else in S02 (aliases for fuzzy match, office_name vs. name distinction) depends on ward *names*, which are themselves only UNVERIFIED per §2/§3 — so the risk is downstream (aliases would be built on an unverified base list), not a direct contradiction of S02's schema itself.
