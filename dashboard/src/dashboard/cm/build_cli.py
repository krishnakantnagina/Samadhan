"""Rebuild the CM registry from the scraped data: `uv run python -m dashboard.cm.build_cli` (from dashboard/).

Reads Samadhan's live `offices` table (read-only, service key from the repo-root .env) when it can; otherwise builds without it.
Writes only the local SQLite registry (local-research/data/cm_registry.db). Manual edits in the registry survive.
"""

import sys

from dotenv import load_dotenv

from dashboard.cm import registry


def fetch_live_offices() -> list[dict] | None:
    """Samadhan's offices (read-only) or None if the database is not reachable/configured."""
    try:
        from dashboard.db import get_client

        return get_client().table("offices").select("id,department,level,name,office_name,active").execute().data
    except Exception as exc:  # noqa: BLE001 -- the registry must still build offline
        print(f"note: live offices not loaded ({exc.__class__.__name__}); building without them", file=sys.stderr)
        return None


def main() -> None:
    load_dotenv()
    conn = registry.connect()
    summary = registry.build(conn, live_offices=fetch_live_offices())
    print({k: v for k, v in summary.items() if k != "unmatched_departments"})
    for source, names in summary["unmatched_departments"].items():
        print(f"unmatched department names in {source}: {sum(names.values())} rows, {len(names)} names")


if __name__ == "__main__":
    main()
