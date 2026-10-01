"""Create the demo accounts: `uv run python -m dashboard.cm.make_demo_accounts` (from dashboard/).

Writes, both git-excluded (local-research/ is excluded via .git/info/exclude):
  local-research/demo_accounts.json  hashed credentials the app reads
  local-research/DEMO_ACCOUNTS.md    plain-text usernames and passwords for testers (DEMO ONLY: never reuse these passwords anywhere)
Refuses to overwrite existing accounts unless --force, so a teammate's passwords are not silently changed.
One dept_head per Samadhan department, one office_officer per ward-52 office (the demo ward used in the seed data), a triage desk, a CM admin.
"""

import json
import secrets
import sys

from dashboard.cm import accounts
from dashboard.cm.departments import LIVE_MAP

OUT_DIR = accounts.DEFAULT_ACCOUNTS_FILE.parent
SHORT = {"Jal Vibhag": "jal", "Bijli Vibhag": "bijli", "Lok Nirman Vibhag": "pwd", "Nagar Nigam Sanitation": "sanitation"}
WARD_OFFICE = "Ward मिसरोद {short} Office (DEMO)"  # seed_departments.sql naming for ward 52 (Misrod)
WATER_WARD_OFFICE = "Ward मिसरोद Office"  # as stored in the offices table for Jal Vibhag ward 52 (checked 2026-10-01)


def password() -> str:
    return secrets.token_urlsafe(9)


def build() -> tuple[list[dict], list[tuple[str, str, str, str]]]:
    plain: list[tuple[str, str, str, str]] = []  # username, password, role, description
    records: list[dict] = []

    def add(username: str, role: str, desc: str, **scope) -> None:
        pw = password()
        records.append({"username": username, "role": role, "label": desc, **scope, **accounts.hash_password(pw)})
        plain.append((username, pw, role, desc))

    add("cm.office", "cm_admin", "CM office: sees and manages everything")
    for dept, dept_id in LIVE_MAP.items():
        short = SHORT[dept]
        add(f"{short}.head", "dept_head", f"Head of {dept}: that department only", department=dept, dept_id=dept_id)
        office = WATER_WARD_OFFICE if dept == "Jal Vibhag" else WARD_OFFICE.format(short={"Bijli Vibhag": "Bijli", "Lok Nirman Vibhag": "PWD", "Nagar Nigam Sanitation": "Sanitation"}[dept])
        add(f"{short}.ward52", "office_officer", f"{dept}, ward 52 (Misrod) office officer: that office only, cannot reassign", department=dept, dept_id=dept_id, office_name=office)
    add("triage.desk", "triage", "Triage desk: General Triage queue + every needs_review ticket, can reassign to any department")
    return records, plain


def main() -> None:
    force = "--force" in sys.argv
    if accounts.DEFAULT_ACCOUNTS_FILE.exists() and not force:
        raise SystemExit(f"{accounts.DEFAULT_ACCOUNTS_FILE} exists; use --force to replace it (this changes every demo password)")
    records, plain = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    accounts.DEFAULT_ACCOUNTS_FILE.write_text(json.dumps({"accounts": records}, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = ["# Samadhan CM-office DEMO accounts", "",
             "DEMO ONLY. Plain-text passwords for testers. This file is git-excluded; do not commit, paste into tickets, or reuse these passwords.",
             "The legacy shared DASHBOARD_PASSWORD also works as user `admin` (cm_admin).", "",
             "| username | password | role | what it sees |", "|---|---|---|---|"]
    lines += [f"| `{u}` | `{p}` | {r} | {d} |" for u, p, r, d in plain]
    lines += ["", "Scoping is enforced by the app only (the dashboard uses the Supabase service key), so this is a demo of separation, not a security boundary.",
              "Office names for ward accounts must equal `offices.office_name` in the database; if an officer sees no tickets, compare them."]
    (OUT_DIR / "DEMO_ACCOUNTS.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(records)} accounts written to {OUT_DIR} (hashes in demo_accounts.json, plain text in DEMO_ACCOUNTS.md)")


if __name__ == "__main__":
    main()
