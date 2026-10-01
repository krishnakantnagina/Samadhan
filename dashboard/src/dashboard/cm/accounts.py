"""Demo-grade accounts and roles for the CM-office system.

Roles:  cm_admin (everything) | dept_head (one department) | office_officer (one office, no reassigning) | evaluator (Human Evaluation queue + every needs_review ticket).
Accounts live in a JSON file (PBKDF2-SHA256, per-account salt) outside git; the plain-text demo passwords live in a separate git-excluded
note for testers. The shared DASHBOARD_PASSWORD keeps working as user `admin` (cm_admin) so nothing that exists today breaks.

LIMIT (say it out loud in any demo): the dashboard talks to Supabase with the service key, which bypasses row-level security. Scoping here
is enforced by the app, so it stops an honest officer from seeing another department, but it is NOT a security boundary. Real separation
needs Supabase Auth + row-level security per department (docs: CM_OFFICE_DASHBOARD_DESIGN.md section 2).
"""

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

ROLES = ("cm_admin", "dept_head", "office_officer", "evaluator")
ITERATIONS = 200_000
DEFAULT_ACCOUNTS_FILE = Path(__file__).resolve().parents[4] / "local-research" / "demo_accounts.json"

# page key -> roles that may open it
PAGE_ACCESS: dict[str, tuple[str, ...]] = {
    "command": ROLES,
    "search": ROLES,
    "human_eval": ("cm_admin", "evaluator"),
    "area": ("cm_admin", "dept_head"),
    "departments": ("cm_admin",),
    "my_department": ("dept_head",),
    "geography": ("cm_admin",),
    "services": ("cm_admin", "dept_head", "evaluator"),
    "tickets": ROLES,
    "routing_lab": ("cm_admin", "evaluator"),
    "public_flow": ("cm_admin",),
    "data": ("cm_admin",),
    "accounts": ("cm_admin",),
}


@dataclass(frozen=True)
class Account:
    username: str
    role: str
    department: str | None = None  # Samadhan's department text (tickets.department), for dept_head / office_officer
    office_name: str | None = None  # tickets' office_name, for office_officer
    dept_id: str | None = None  # registry id of that department
    label: str = ""
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def demo_only(self) -> bool:
        """The public Demo button: sample data only, never the live database, and no account or data-source admin pages."""
        return bool(self.extra.get("demo_only"))

    def can_open(self, page: str) -> bool:
        if self.demo_only and page in ("accounts", "data"):
            return False
        return self.role in PAGE_ACCESS.get(page, ())

    @property
    def can_reassign(self) -> bool:
        return self.role in ("cm_admin", "dept_head", "evaluator")

    def reassign_departments(self) -> set[str] | None:
        """Departments this account may reassign TO: None = any (admin, evaluator), its own department only for a head."""
        if self.role == "dept_head" and self.department:
            return {self.department}
        return None


def hash_password(password: str, salt: str | None = None, iterations: int = ITERATIONS) -> dict[str, Any]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations).hex()
    return {"salt": salt, "hash": digest, "iterations": iterations}


def verify_password(password: str, record: dict[str, Any]) -> bool:
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(record["salt"]), int(record["iterations"])).hex()
    return hmac.compare_digest(candidate, record["hash"])


def load_accounts(path: Path | str | None = None) -> list[dict[str, Any]]:
    p = Path(path or os.environ.get("DASHBOARD_ACCOUNTS_FILE") or DEFAULT_ACCOUNTS_FILE)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))["accounts"]


def authenticate(username: str, password: str, accounts: list[dict[str, Any]], legacy_password: str | None = None) -> Account | None:
    """The account for these credentials, or None. Same work is done for unknown users so timing does not reveal which exist."""
    username = username.strip().lower()
    if legacy_password and username == "admin":
        if hmac.compare_digest(password.encode(), legacy_password.encode()):
            return Account("admin", "cm_admin", label="CM office (shared dashboard password)")
        return None
    record = next((a for a in accounts if a["username"].lower() == username), None)
    dummy = {"salt": "00" * 16, "hash": "0" * 64, "iterations": ITERATIONS}
    ok = verify_password(password, record if record else dummy)
    if record is None or not ok or record["role"] not in ROLES:
        return None
    return Account(record["username"], record["role"], record.get("department"), record.get("office_name"), record.get("dept_id"), record.get("label", ""))


def scope_tickets(df: pd.DataFrame, account: Account) -> pd.DataFrame:
    """The tickets this account may see (df has `department`, `office_name`, `status`). Fails closed: a scoped role with no scope sees nothing."""
    if df.empty or account.role == "cm_admin":
        return df
    if account.role == "evaluator":
        return df[(df["department"] == "Human Evaluation") | (df["status"] == "needs_review")]
    if account.role == "dept_head":
        return df[df["department"] == account.department] if account.department else df.iloc[0:0]
    if account.role == "office_officer":
        if not (account.department and account.office_name):
            return df.iloc[0:0]
        return df[(df["department"] == account.department) & (df["office_name"] == account.office_name)]
    return df.iloc[0:0]


def guest_demo() -> Account:
    """Account behind the home page's Demo button: sees everything except accounts / data sources, on the invented demo dataset only."""
    return Account("demo", "cm_admin", label="Demo visitor (sample data)", extra={"demo_only": True})


def guest_allowed() -> bool:
    return os.environ.get("DASHBOARD_ALLOW_GUEST", "1").strip().lower() not in ("0", "false", "no", "off")
