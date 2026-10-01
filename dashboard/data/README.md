# Dashboard data snapshot (deployed servers)

A small copy of public Madhya Pradesh government figures so the hosted dashboard matches the laptop one. The Lead approved committing it (2026-10-01) as an exception to the rule that scraped research stays in the git-excluded `local-research/` folder.

| File | What it is | Source |
|---|---|---|
| `cm_registry.db` | Departments, services, divisions, districts, demo offices (SQLite, no audit entries) | built by `dashboard.cm.build_cli` from public listings (mp.gov.in, mpedistrict, mpinfo.org) |
| `cmhelpline_overview.json` | CM Helpline 181 headline totals | cmhelpline.mp.gov.in, scraped 2026-10-01 |
| `cmhelpline_schemes.csv` | Scheme names and departments | cmhelpline.mp.gov.in, scraped 2026-10-01 |

Nothing here is Samadhan citizen data. The app reads `local-research/data/` first when it exists, then this folder; set `DASHBOARD_DATA_DIR` to override both.
