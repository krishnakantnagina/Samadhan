"""Remove one citizen's personal data on request (see app/data_rights.py for exactly what goes and what stays).

    cd backend
    uv run --env-file ../.env python scripts/delete_citizen_data.py --phone 9876543210          # DRY RUN: only lists what it would do
    uv run --env-file ../.env python scripts/delete_citizen_data.py --phone 9876543210 --yes    # does it (cannot be undone)

Uses the real database (the service key in .env). Check the phone number and the request with the citizen first.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth, data_rights
from app.db import get_client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phone", required=True, help="the citizen's mobile number")
    parser.add_argument("--yes", action="store_true", help="really delete (without it nothing is changed)")
    args = parser.parse_args()

    try:
        auth.normalise_phone(args.phone)
    except auth.AuthError as exc:
        print("Not a valid mobile number:", exc.message)
        return 2

    client = get_client()
    found = data_rights.plan(client, args.phone)
    if found is None:
        print("No registered citizen with that number. Nothing to do.")
        return 0
    print(f"Registered citizen found. Complaints linked: {len(found.complaint_ids)} {found.complaint_ids}")
    print(f"Voice recordings to delete: {len(found.audio_paths)}; saved logins to delete: {found.login_sessions}")
    print("The complaints themselves stay, with the link to this number removed.")
    if not args.yes:
        print("DRY RUN: nothing was changed. Add --yes to delete.")
        return 0
    data_rights.erase(client, args.phone)
    print("Done: phone number, logins and recordings removed; complaints unlinked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
