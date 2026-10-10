"""Create one login per routing desk: `uv run --with pyyaml python -m dashboard.cm.make_desk_accounts` (from dashboard/).

For every department in specs/registry/district_desks.yaml: one office_officer account per district (scope: district, in each of the 55 districts of
specs/registry/districts.yaml) or one state desk (scope: state). The username is "<prefix>.<district>" (or "<prefix>.state"); the office_name matches
exactly what migration 007 writes into the offices table, so a login scopes to its desk once that migration is applied to the database it reads.

Writes, both under local-research/ (git-excluded; never commit, never reuse these passwords):
  local-research/demo_accounts.json  -- the hashed credentials the app reads; EXISTING accounts (the demo logins) are kept, desk logins are merged in by username
  local-research/DESK_ACCOUNTS.md     -- the plain-text usernames and passwords, grouped by department

Re-running regenerates every desk password (and leaves the hand-made demo accounts untouched). Pass --dry-run to print the counts without writing.
"""

import json
import re
import secrets
import sys
from pathlib import Path

import yaml

from dashboard.cm import accounts

ROOT = accounts.DEFAULT_ACCOUNTS_FILE.parents[1]  # repo root (local-research/ is DEFAULT_ACCOUNTS_FILE.parent)
SPECS = ROOT / "specs"
SKIP = {"human_evaluation"}  # the review queue, not a government department
OUT_JSON = accounts.DEFAULT_ACCOUNTS_FILE
OUT_MD = OUT_JSON.parent / "DESK_ACCOUNTS.md"


def _load_departments() -> dict[str, str]:
    """service key -> department display name, from the per-service specs (same source as gen_district_desks.py)."""
    out: dict[str, str] = {}
    for path in sorted(SPECS.glob("*.yaml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        if spec.get("service") and spec["service"] not in SKIP:
            out[spec["service"]] = spec["department"]
    return out


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def build() -> tuple[list[dict], list[tuple[str, str, str, str, str]]]:
    desks = yaml.safe_load((SPECS / "registry" / "district_desks.yaml").read_text(encoding="utf-8"))["services"]
    districts = yaml.safe_load((SPECS / "registry" / "districts.yaml").read_text(encoding="utf-8"))["districts"]
    departments = _load_departments()
    missing = set(departments) - set(desks)
    if missing:
        sys.exit(f"district_desks.yaml has no desk for: {sorted(missing)} -- regenerate it first")

    records: list[dict] = []
    plain: list[tuple[str, str, str, str, str]] = []  # username, password, department, district, desk (office_name)

    def add(username: str, department: str, office_name: str, label: str, district: str) -> None:
        pw = secrets.token_urlsafe(9)
        records.append({"username": username, "role": "office_officer", "department": department,
                        "office_name": office_name, "label": label, **accounts.hash_password(pw)})
        plain.append((username, pw, department, district, office_name))

    for service, dept in sorted(departments.items(), key=lambda kv: kv[1]):
        v = desks[service]
        prefix, designation = v["prefix"].lower(), v["designation"]
        if v["scope"] == "district":
            for d in districts:
                add(f"{prefix}.{_slug(d['name_en'])}", dept, f"{designation}, {d['name_en']}",
                    f"{designation} — {dept}, {d['name_en']}", d["name_en"])
        else:
            add(f"{prefix}.state", dept, designation, f"{designation} — {dept} (state desk)", "(state desk)")
    return records, plain


def _write_markdown(plain: list[tuple[str, str, str, str, str]]) -> None:
    lines = [
        "# Samadhan desk logins (ALL district and state desks)",
        "",
        "DEMO / INTERNAL. Plain-text passwords. This file is git-excluded; do not commit, paste into tickets, or reuse these passwords.",
        "One `office_officer` login per routing desk. A desk is a designation, not a person; the login scopes to its desk once migration 007 is applied to the database the app reads.",
        f"Generated for {len(plain)} desks. Admin login: user `admin` + DASHBOARD_PASSWORD, or the demo accounts in DEMO_ACCOUNTS.md.",
        "",
    ]
    current = None
    for username, pw, dept, district, office in sorted(plain, key=lambda r: (r[2], r[3])):
        if dept != current:
            current = dept
            lines += ["", f"## {dept}", "", "| username | password | district | desk |", "|---|---|---|---|"]
        lines.append(f"| `{username}` | `{pw}` | {district} | {office} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    records, plain = build()
    n_state = sum(1 for r in records if r["office_name"] == r["label"].split(" — ")[0] and "(state desk)" in r["label"])
    print(f"built {len(records)} desk accounts ({len(records) - n_state} district + {n_state} state)")
    if "--dry-run" in sys.argv:
        print("dry run: nothing written")
        return
    existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))["accounts"] if OUT_JSON.exists() else []
    by_user = {a["username"].lower(): a for a in existing}
    kept = len(by_user)
    for r in records:
        by_user[r["username"].lower()] = r
    OUT_JSON.write_text(json.dumps({"accounts": list(by_user.values())}, indent=1, ensure_ascii=False), encoding="utf-8")
    _write_markdown(plain)
    print(f"wrote {OUT_JSON} ({len(by_user)} accounts total; {kept} pre-existing kept)")
    print(f"wrote {OUT_MD} ({len(plain)} rows)")


if __name__ == "__main__":
    main()
