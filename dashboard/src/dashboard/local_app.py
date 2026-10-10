"""Run the officer dashboard against the PRIVATE local Postgres (devdb, port 5544), not the live Supabase. TEST ONLY.

From dashboard/:
    uv run --with "psycopg[binary]" streamlit run src/dashboard/local_app.py --server.address localhost

Sign in with any desk login from local-research/DESK_ACCOUNTS.md (e.g. ahd.shajapur), a demo account, or admin + the
DASHBOARD_PASSWORD set below. It shows the complaints filed through the local test backend, which live in the same devdb.

How it stays off the live database: the SUPABASE_* vars are overwritten with dummy values before anything imports them,
and dashboard.db.get_client is replaced with the local Postgres adapter (dashboard.local_client.LocalClient).
"""

import os
import runpy
from pathlib import Path

# 1. never let this process reach the live database (config.py requires these to be non-empty).
os.environ["SUPABASE_URL"] = "http://127.0.0.1:1"
os.environ["SUPABASE_SERVICE_KEY"] = "local-dev-dummy"
os.environ.setdefault("SUPABASE_ANON_KEY", "local-dev-dummy")
os.environ.setdefault("DASHBOARD_PASSWORD", "localdev")  # admin login; desk logins use local-research/demo_accounts.json

# 2. point the dashboard's client factory at the private Postgres, before app.py binds `get_client`.
from dashboard import db
from dashboard.local_client import LocalClient

db.get_client = lambda: LocalClient()

# 3. run the real CM-office dashboard in this process (__main__, so its `if __name__ == "__main__": main()` fires).
# cm_app.py is the account-based dashboard: desk logins (username + password) and per-desk ticket scoping.
runpy.run_path(str(Path(__file__).with_name("cm_app.py")), run_name="__main__")
