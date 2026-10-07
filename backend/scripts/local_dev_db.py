"""A private, throw-away Postgres for testing Samadhan without touching the live Supabase.

    python scripts/local_dev_db.py setup     # create the cluster (once), start it, load schema + seeds + migrations 002..004
    python scripts/local_dev_db.py start | stop | status | reset | tickets

Data lives in <repo>/local-research/devdb/ (git-excluded). Port 5544, localhost only, trust auth (no password): fine because it only listens on 127.0.0.1
and holds nothing but demo data. It is a separate server from any Postgres already on your machine (port 5432). `reset` deletes and rebuilds it.
Needs PostgreSQL 14+ binaries; set PG_BIN if they are not under C:/Program Files/PostgreSQL/*/bin.
"""

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "local-research" / "devdb"
DATA = DEV / "pgdata"
PORT = os.environ.get("LOCAL_PG_PORT", "5544")
DB = "samadhan_scratch"
FILES = ["schema.sql", "seed.sql", "seed_departments.sql", "migrations/002_registration_and_location.sql",
         "migrations/003_human_evaluation_cutover.sql", "migrations/004_all_department_offices.sql", "migrations/005_district_offices.sql", "seed_demo_district_offices.sql"]


def pg_bin() -> Path:
    env = os.environ.get("PG_BIN")
    if env:
        return Path(env)
    found = sorted(glob.glob("C:/Program Files/PostgreSQL/*/bin"))
    if not found:
        raise SystemExit("PostgreSQL binaries not found; set PG_BIN")
    return Path(found[-1])


def run(exe: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([str(pg_bin() / exe), *args], check=check, capture_output=True, text=True, encoding="utf-8", errors="replace")


def psql(*args: str, db: str = DB, check: bool = True) -> subprocess.CompletedProcess:
    return run("psql.exe", "-h", "127.0.0.1", "-p", PORT, "-U", "postgres", "-d", db, "-v", "ON_ERROR_STOP=1", "-q", *args, check=check)


def running() -> bool:
    return run("pg_ctl.exe", "-D", str(DATA), "status", check=False).returncode == 0


def start() -> None:
    if running():
        print("already running")
        return
    # Popen, not run(): pg_ctl's child keeps the pipes open, so waiting for them would hang
    subprocess.Popen([str(pg_bin() / "pg_ctl.exe"), "-D", str(DATA), "-o", f"-p {PORT} -c listen_addresses=127.0.0.1", "-l", str(DEV / "pg.log"), "start"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if run("pg_isready.exe", "-h", "127.0.0.1", "-p", PORT, check=False).returncode == 0:
            print(f"running on 127.0.0.1:{PORT}")
            return
        import time
        time.sleep(0.5)
    raise SystemExit("did not start; see " + str(DEV / "pg.log"))


def setup() -> None:
    DEV.mkdir(parents=True, exist_ok=True)
    if not DATA.exists():
        run("initdb.exe", "-D", str(DATA), "-U", "postgres", "-A", "trust", "-E", "UTF8")
    start()
    psql("-c", "DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;",
         "-c", "DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;", db="postgres")
    if run("psql.exe", "-h", "127.0.0.1", "-p", PORT, "-U", "postgres", "-d", "postgres", "-At", "-c", f"select 1 from pg_database where datname='{DB}'").stdout.strip() != "1":
        psql("-c", f"create database {DB}", db="postgres")
    for f in FILES:
        psql("-f", str(ROOT / "database" / f))
        print("loaded", f)
    n = psql("-At", "-c", "select count(*) || ' offices, ' || count(distinct department) || ' departments' from offices").stdout.strip()
    print("ready:", n)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "setup":
        setup()
    elif cmd == "start":
        start()
    elif cmd == "stop":
        run("pg_ctl.exe", "-D", str(DATA), "-m", "fast", "stop", check=False)
        print("stopped")
    elif cmd == "status":
        print("running" if running() else "stopped")
    elif cmd == "reset":
        run("pg_ctl.exe", "-D", str(DATA), "-m", "immediate", "stop", check=False)
        shutil.rmtree(DATA, ignore_errors=True)
        setup()
    elif cmd == "tickets":
        print(psql("-c", "select complaint_id, department, status, office_id, left(original_text, 60) as text, created_at::timestamp(0) from tickets order by id desc limit 20").stdout)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
