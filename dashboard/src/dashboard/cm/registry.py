"""CM-office registry: departments, sub-offices, services and geography in one local SQLite file.

Why SQLite and not the live Supabase: this is a management/reference store, it must be editable by the CM office without
writing to the shared ticket database, and it can later move into a `core` schema (docs: CM_OFFICE_DASHBOARD_DESIGN.md).
Rule carried over from docs/ARCHITECTURE_DEPARTMENTS.md / S09: never invent official data. A department x district office that
nobody has onboarded is shown as "not onboarded", never made up. Every office row has a status (demo / unverified / verified).

Data comes from `local-research/data/` (git-excluded scrapes of mp.gov.in, mpedistrict, CM Helpline, mpinfo.org). The registry
file itself is also kept there. Manual edits (department status/notes, manually added offices) survive a rebuild; scraped tables
are replaced on rebuild. Every manual edit is written to `audit_log`.
"""

import csv
import difflib
import json
import os
import re
import sqlite3
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dashboard.cm.departments import ALL_DEPARTMENTS, DEPARTMENTS, LIVE_MAP

REPO_ROOT = Path(__file__).resolve().parents[4]
def _data_dir() -> Path:
    """DASHBOARD_DATA_DIR, else the git-excluded local-research/data when it has a registry (a developer laptop), else the committed snapshot in dashboard/data (hosted servers)."""
    if os.environ.get("DASHBOARD_DATA_DIR"):
        return Path(os.environ["DASHBOARD_DATA_DIR"])
    local = REPO_ROOT / "local-research" / "data"
    return local if (local / "cm_registry.db").exists() else REPO_ROOT / "dashboard" / "data"


DATA_DIR = _data_dir()
DEFAULT_DB = DATA_DIR / "cm_registry.db"

DEPT_STATUSES = ("catalogued", "planned", "demo", "live")  # catalogued = known to exist, not onboarded in Samadhan
OFFICE_STATUSES = ("demo", "unverified", "verified")
OFFICE_LEVELS = ("state", "division", "district", "tehsil", "block", "ward", "zone", "other")

SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
  id TEXT PRIMARY KEY, name_en TEXT NOT NULL, name_hi TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'catalogued', live_name TEXT, official45 INTEGER NOT NULL DEFAULT 1, notes TEXT NOT NULL DEFAULT '', updated_at TEXT
);
CREATE TABLE IF NOT EXISTS aliases (dept_id TEXT NOT NULL, alias TEXT NOT NULL, source TEXT NOT NULL, score REAL NOT NULL);
CREATE TABLE IF NOT EXISTS services (
  id INTEGER PRIMARY KEY AUTOINCREMENT, dept_id TEXT, source TEXT NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL DEFAULT '',
  apply_url TEXT NOT NULL DEFAULT '', deadline_urban TEXT NOT NULL DEFAULT '', deadline_rural TEXT NOT NULL DEFAULT '',
  fee TEXT NOT NULL DEFAULT '', documents TEXT NOT NULL DEFAULT '[]', detail_url TEXT NOT NULL DEFAULT '', raw_department TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS services_dept ON services (dept_id);
CREATE TABLE IF NOT EXISTS divisions (name TEXT PRIMARY KEY, std_code TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS districts (
  name TEXT PRIMARY KEY, division TEXT NOT NULL, std_code TEXT NOT NULL DEFAULT '', area_sq_km INTEGER, population_2011 INTEGER,
  headquarters TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS offices (
  id INTEGER PRIMARY KEY AUTOINCREMENT, dept_id TEXT, level TEXT NOT NULL, district TEXT, name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'unverified', source TEXT NOT NULL DEFAULT 'manual', live_office_id INTEGER, notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
"""


# --- name matching ----------------------------------------------------------------------------------------------

_DROP = ("विभाग", "मध्यप्रदेश", "मध्य प्रदेश")
_SYNONYMS = (("और", "एवं"), ("तथा", "एवं"), ("निःशक्तजन", "दिव्यांगजन"), ("सशक्तिकरण", "कल्याण"))

# Reviewed by hand: the same department under an older, merged or extended name. Each is a judgement, shown with score 0.9 so it is visible.
MANUAL_ALIASES_RAW = {
    "पशुपालन एवं डेयरी विभाग": "animal_husbandry",  # dairy added to the department's name
    "लोक स्वास्थ्य एवं चिकित्सा शिक्षा विभाग": "public_health_family_welfare",  # merged department, also covers medical education
    "लोक स्वास्थ्य और चिकित्सा शिक्षा": "public_health_family_welfare",
    "नगरीय विकास एवं पर्यावरण": "urban_development_housing",  # older name of a merged department
    "नगरीय प्रशासन एवं विकास": "urban_development_housing",  # older name of a merged department
    "आदिम जाति कल्याण": "tribal_affairs",  # older name of the Tribal Affairs department
}


def norm_hi(name: str) -> str:
    """Comparable form of a Hindi department name: NFC, no joiners, no 'Vibhag'/'Madhya Pradesh', one 'evam', no punctuation/spaces.
    The three MP portals spell the same department differently (', मध्यप्रदेश' suffix, 'और' vs 'एवं', joiner characters)."""
    s = unicodedata.normalize("NFC", name).replace("‍", "").replace("‌", "")
    for word in _DROP:
        s = s.replace(word, "")
    for old, new in _SYNONYMS:
        s = s.replace(old, new)
    return re.sub(r"[\s,.\-()/]+", "", s)


_MANUAL = {}  # filled below, after norm_hi exists


def match_department(name: str, threshold: float = 0.82) -> tuple[str, float] | None:
    """Best registry department id for a portal's department name, or None. Exact normalised match scores 1.0, a reviewed manual alias 0.9,
    otherwise a fuzzy ratio (kept only at or above the threshold)."""
    key = norm_hi(name)
    if not key:
        return None
    best: tuple[str, float] | None = None
    for dept_id, _en, hi in ALL_DEPARTMENTS:
        cand = norm_hi(hi)
        score = 1.0 if cand == key else difflib.SequenceMatcher(None, key, cand).ratio()
        if best is None or score > best[1]:
            best = (dept_id, score)
    if best and best[1] == 1.0:
        return best
    if key in _MANUAL:
        return _MANUAL[key], 0.9
    return best if best and best[1] >= threshold else None


_MANUAL.update({norm_hi(k): v for k, v in MANUAL_ALIASES_RAW.items()})


# --- connection / writes ----------------------------------------------------------------------------------------

def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def audit(conn: sqlite3.Connection, actor: str, action: str, target: str, detail: str = "") -> None:
    conn.execute("INSERT INTO audit_log (ts, actor, action, target, detail) VALUES (?,?,?,?,?)", (_now(), actor, action, target, detail))


def set_department(conn: sqlite3.Connection, dept_id: str, *, status: str, notes: str, actor: str) -> None:
    if status not in DEPT_STATUSES:
        raise ValueError(f"status must be one of {DEPT_STATUSES}")
    before = conn.execute("SELECT status, notes FROM departments WHERE id=?", (dept_id,)).fetchone()
    if before is None:
        raise KeyError(dept_id)
    conn.execute("UPDATE departments SET status=?, notes=?, updated_at=? WHERE id=?", (status, notes, _now(), dept_id))
    audit(conn, actor, "department.update", dept_id, f"status {before['status']}->{status}; notes changed={before['notes'] != notes}")
    conn.commit()


def add_office(conn: sqlite3.Connection, *, dept_id: str | None, level: str, district: str | None, name: str, status: str,
               notes: str, actor: str) -> int:
    if level not in OFFICE_LEVELS or status not in OFFICE_STATUSES:
        raise ValueError("invalid level or status")
    if not name.strip():
        raise ValueError("office name is required")
    cur = conn.execute(
        "INSERT INTO offices (dept_id, level, district, name, status, source, notes) VALUES (?,?,?,?,?,'manual',?)",
        (dept_id, level, district, name.strip(), status, notes),
    )
    audit(conn, actor, "office.add", f"{dept_id or 'system'}/{level}/{district or '-'}", name.strip())
    conn.commit()
    return int(cur.lastrowid)


def delete_office(conn: sqlite3.Connection, office_id: int, *, actor: str) -> None:
    row = conn.execute("SELECT * FROM offices WHERE id=?", (office_id,)).fetchone()
    if row is None or row["source"] != "manual":
        raise ValueError("only manually added offices can be deleted")
    conn.execute("DELETE FROM offices WHERE id=?", (office_id,))
    audit(conn, actor, "office.delete", f"{row['dept_id']}/{row['level']}/{row['district']}", row["name"])
    conn.commit()


# --- reads ------------------------------------------------------------------------------------------------------

def rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def departments_overview(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows(conn, """
        SELECT d.id, d.name_en, d.name_hi, d.status, d.live_name, d.notes, d.official45,
          (SELECT COUNT(*) FROM services s WHERE s.dept_id=d.id AND s.source='mp.gov.in') AS services_mp,
          (SELECT COUNT(*) FROM services s WHERE s.dept_id=d.id AND s.source='mpedistrict') AS services_mped,
          (SELECT COUNT(*) FROM services s WHERE s.dept_id=d.id AND s.source='cmhelpline') AS schemes_cmh,
          (SELECT COUNT(*) FROM offices o WHERE o.dept_id=d.id) AS offices,
          (SELECT COUNT(DISTINCT o.district) FROM offices o WHERE o.dept_id=d.id AND o.district IS NOT NULL) AS districts_covered
        FROM departments d ORDER BY services_mp DESC, d.name_en""")


def department_services(conn: sqlite3.Connection, dept_id: str, source: str | None = None) -> list[dict[str, Any]]:
    sql, args = "SELECT * FROM services WHERE dept_id=?", [dept_id]
    if source:
        sql, args = sql + " AND source=?", [dept_id, source]
    out = rows(conn, sql + " ORDER BY title", tuple(args))
    for r in out:
        r["documents"] = json.loads(r["documents"] or "[]")
    return out


def coverage_matrix(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """One row per department, one column per district: the office status there, or 'not onboarded'. Never invents an office."""
    districts = [r["name"] for r in conn.execute("SELECT name FROM districts ORDER BY division, name")]
    cells: dict[tuple[str, str], str] = {}
    rank = {"verified": 3, "unverified": 2, "demo": 1}
    for o in conn.execute("SELECT dept_id, district, status FROM offices WHERE dept_id IS NOT NULL AND district IS NOT NULL"):
        key = (o["dept_id"], o["district"])
        if rank[o["status"]] > rank.get(cells.get(key, ""), 0):
            cells[key] = o["status"]
    return [
        {"department": d["name_en"], "dept_id": d["id"], **{dist: cells.get((d["id"], dist), "not onboarded") for dist in districts}}
        for d in conn.execute("SELECT id, name_en FROM departments ORDER BY name_en").fetchall()
    ]


# --- build from scraped data ------------------------------------------------------------------------------------

def _int(value: str) -> int | None:
    return int(value) if str(value).strip().isdigit() else None


def build(conn: sqlite3.Connection, data_dir: Path = DATA_DIR, live_offices: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """(Re)load everything scraped. Keeps manual edits: department status/notes, manual offices, audit log."""
    official = {d[0] for d in DEPARTMENTS}
    for dept_id, en, hi in ALL_DEPARTMENTS:
        live = next((k for k, v in LIVE_MAP.items() if v == dept_id), None)
        conn.execute("INSERT OR IGNORE INTO departments (id, name_en, name_hi, status, live_name, official45) VALUES (?,?,?,?,?,?)",
                     (dept_id, en, hi, "demo" if live else "catalogued", live, int(dept_id in official)))
        conn.execute("UPDATE departments SET name_en=?, name_hi=?, live_name=?, official45=? WHERE id=?", (en, hi, live, int(dept_id in official), dept_id))
    for table in ("services", "aliases", "divisions", "districts"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM offices WHERE source='supabase'")
    summary: dict[str, Any] = {"unmatched_departments": {}}

    def add_services(source: str, records: list[dict[str, Any]]) -> None:
        unmatched: dict[str, int] = {}
        seen_alias: set[tuple[str, str]] = set()
        for r in records:
            raw = r.get("department", "")
            m = match_department(raw) if raw else None
            if raw and m is None:
                unmatched[raw] = unmatched.get(raw, 0) + 1
            if m and (source, raw) not in seen_alias:
                seen_alias.add((source, raw))
                conn.execute("INSERT INTO aliases (dept_id, alias, source, score) VALUES (?,?,?,?)", (m[0], raw, source, round(m[1], 3)))
            conn.execute(
                "INSERT INTO services (dept_id, source, title, category, apply_url, deadline_urban, deadline_rural, fee, documents, detail_url, raw_department)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (m[0] if m else None, source, r.get("title", ""), r.get("category", ""), r.get("apply_url", ""), r.get("deadline_urban", ""),
                 r.get("deadline_rural", ""), r.get("fee", ""), json.dumps(r.get("documents", []), ensure_ascii=False), r.get("detail_url", ""), raw))
        summary[source] = len(records)
        if unmatched:
            summary["unmatched_departments"][source] = unmatched

    p = data_dir / "mp_gov_services.csv"
    if p.exists():
        add_services("mp.gov.in", [r for r in csv.DictReader(p.open(encoding="utf-8-sig")) if r["title"]])
    p = data_dir / "mpedistrict" / "services.jsonl"
    if p.exists():
        recs = [json.loads(line) for line in p.open(encoding="utf-8")]
        add_services("mpedistrict", [{"title": r["service"], "department": r["department"], "deadline_urban": r["deadline_urban"],
                                      "deadline_rural": r["deadline_rural"], "fee": r["fee_lsk"], "documents": r["documents"],
                                      "apply_url": r["online_link"], "detail_url": r["detail_url"]} for r in recs])
    p = data_dir / "cmhelpline_schemes.csv"
    if p.exists():
        add_services("cmhelpline", [{"title": r["scheme"], "department": r["department"], "detail_url": r["url"]}
                                    for r in csv.DictReader(p.open(encoding="utf-8-sig")) if r["scheme"]])
    g = data_dir / "geography"
    if (g / "divisions.csv").exists():
        for r in csv.DictReader((g / "divisions.csv").open(encoding="utf-8-sig")):
            conn.execute("INSERT INTO divisions (name, std_code) VALUES (?,?)", (r["division"], r["std_code"]))
        for r in csv.DictReader((g / "districts.csv").open(encoding="utf-8-sig")):
            conn.execute("INSERT INTO districts VALUES (?,?,?,?,?,?,?)", (r["district"], r["division"], r["std_code"], _int(r["area_sq_km"]),
                                                                          _int(r["population_2011"]), r["headquarters"], r["district_email"]))
        summary["districts"] = conn.execute("SELECT COUNT(*) FROM districts").fetchone()[0]
    home = {o["department"]: o.get("name") for o in live_offices or [] if o["level"] == "district"}  # a ward lies in its department's district office
    for o in live_offices or []:
        dept = LIVE_MAP.get(o["department"])
        district = o.get("name") if o["level"] == "district" else home.get(o["department"], "Madhya Pradesh")
        conn.execute(
            "INSERT INTO offices (dept_id, level, district, name, status, source, live_office_id, notes) VALUES (?,?,?,?,?,'supabase',?,?)",
            (dept, o["level"], district, o.get("office_name") or o["name"], "demo", o["id"],
             "Samadhan demo office" + ("" if dept else " (system desk, not a government department)")))
    summary["offices_from_supabase"] = len(live_offices or [])
    conn.commit()
    return summary
