"""Logins that belong to a desk (an office or post), not to a person (migration 008).

A complaint is routed to an office; officers are transferred. So the CM office manages ACCESS to a desk: it gives a login, takes it away, resets its password, or hands the whole desk over
to a new person. None of this touches a ticket: tickets stay on the desk, whoever holds the key.

Only a salted PBKDF2 hash is stored. A new or reset login gets a temporary password that is shown once to the person who created it, and the holder must choose their own at the first login.
Every function takes the Supabase `client` (a fake in tests) and records what happened in dashboard_account_events. The CM office's own accounts (the shared admin password and the accounts
file) are not managed here and cannot be shadowed: those usernames are refused.
"""

import logging
import re
import secrets
from datetime import UTC, datetime
from typing import Any

from dashboard.cm import accounts

logger = logging.getLogger(__name__)

ACCOUNTS = "dashboard_accounts"
EVENTS = "dashboard_account_events"
USERNAME_RE = re.compile(r"^[a-z][a-z0-9._-]{2,39}$")
MIN_PASSWORD = 10
GRANTABLE_ROLES = ("office_officer", "dept_head")  # the CM office's own accounts (cm_admin, evaluator) are not handed out from this screen
RESERVED = {"admin", "demo", "root", "cm.office"}
PUBLIC_COLUMNS = "id,username,role,department,office_name,dept_id,label,active,must_change,created_by,created_at,last_login_at"


class DeskAccessError(ValueError):
    """A request that cannot be done (bad username, taken name, wrong current password...). The message is safe to show to the CM office."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def new_temp_password() -> str:
    return secrets.token_urlsafe(9)


def record_event(client: Any, username: str, action: str, actor: str, detail: str | None = None) -> None:
    """History of who did what to a login. Never raises: the action itself matters more than its log line."""
    try:
        client.table(EVENTS).insert({"username": username, "action": action, "actor": actor or "unknown", "detail": detail}).execute()
    except Exception as exc:  # noqa: BLE001 -- table missing or network
        logger.warning("account event not recorded: %s", type(exc).__name__)


def _one(client: Any, username: str) -> dict[str, Any] | None:
    rows = client.table(ACCOUNTS).select("*").eq("username", username.strip().lower()).execute().data
    return rows[0] if rows else None


def _check_username(client: Any, username: str, taken: set[str]) -> str:
    name = (username or "").strip().lower()
    if not USERNAME_RE.match(name):
        raise DeskAccessError("The username must be 3 to 40 characters: lower-case letters, digits, dot, dash or underscore, starting with a letter.")
    if name in RESERVED or name in {t.lower() for t in taken}:
        raise DeskAccessError(f"The username '{name}' is already used by a CM-office account. Choose another.")
    if _one(client, name):
        raise DeskAccessError(f"The username '{name}' already exists. Choose another, or reset or hand over that login.")
    return name


def list_logins(client: Any, *, office_name: str | None = None) -> list[dict[str, Any]]:
    """Logins without their hashes, newest first; for one desk or for all."""
    query = client.table(ACCOUNTS).select(PUBLIC_COLUMNS)
    if office_name:
        query = query.eq("office_name", office_name)
    return sorted(query.execute().data or [], key=lambda r: str(r.get("created_at", "")), reverse=True)


def list_events(client: Any, *, username: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    query = client.table(EVENTS).select("username,action,actor,detail,created_at")
    if username:
        query = query.eq("username", username)
    return sorted(query.execute().data or [], key=lambda r: str(r.get("created_at", "")), reverse=True)[:limit]


def active_accounts(client: Any) -> list[dict[str, Any]]:
    """The active logins in the shape accounts.authenticate() reads (with the hash), marked source='db'."""
    rows = client.table(ACCOUNTS).select("*").eq("active", True).execute().data or []
    return [{**r, "source": "db"} for r in rows]


def create_login(
    client: Any, *, username: str, role: str, department: str | None, office_name: str | None, actor: str, dept_id: str | None = None, label: str = "",
    taken: set[str] = frozenset(),  # type: ignore[assignment]
) -> str:
    """Make a login for a desk (office_officer) or a whole department (dept_head). Returns the TEMPORARY password: show it once, it is not stored."""
    if role not in GRANTABLE_ROLES:
        raise DeskAccessError("Only office officer and department head logins are handed out from here.")
    if role == "office_officer" and not (office_name and department):
        raise DeskAccessError("An office officer login needs the department and the office (desk).")
    if role == "dept_head" and not department:
        raise DeskAccessError("A department head login needs the department.")
    name = _check_username(client, username, set(taken))
    temp = new_temp_password()
    client.table(ACCOUNTS).insert({
        "username": name, "role": role, "department": department, "office_name": office_name if role == "office_officer" else None, "dept_id": dept_id,
        "label": (label or "").strip()[:200], **accounts.hash_password(temp), "active": True, "must_change": True, "created_by": actor,
    }).execute()
    record_event(client, name, "created", actor, f"{role} on {office_name or department}")
    return temp


def reset_password(client: Any, username: str, actor: str) -> str:
    """A new temporary password for an existing login (forgotten password, or a lost slip of paper). The holder must choose their own again."""
    record = _one(client, username)
    if not record:
        raise DeskAccessError("No such login.")
    temp = new_temp_password()
    client.table(ACCOUNTS).update({**accounts.hash_password(temp), "must_change": True, "updated_at": _now()}).eq("username", record["username"]).execute()
    record_event(client, record["username"], "password_reset", actor)
    return temp


def set_active(client: Any, username: str, active: bool, actor: str) -> None:
    """Take a login away (or give it back). The tickets of its desk are untouched."""
    record = _one(client, username)
    if not record:
        raise DeskAccessError("No such login.")
    client.table(ACCOUNTS).update({"active": bool(active), "updated_at": _now()}).eq("username", record["username"]).execute()
    record_event(client, record["username"], "enabled" if active else "disabled", actor)


def hand_over(
    client: Any, *, office_name: str, department: str, new_username: str, actor: str, dept_id: str | None = None, label: str = "",
    taken: set[str] = frozenset(),  # type: ignore[assignment]
) -> tuple[str, list[str]]:
    """The officer of a desk has changed: switch off every active office-officer login of that desk and make one for the new officer, in that order of safety (the new name is checked first,
    so a bad name changes nothing). Returns (temporary password, usernames switched off). Tickets stay exactly where they are."""
    _check_username(client, new_username, set(taken))  # fail before anything is switched off
    old = [r["username"] for r in list_logins(client, office_name=office_name) if r.get("active") and r.get("role") == "office_officer"]
    for username in old:
        set_active(client, username, False, actor)
        record_event(client, username, "handed_over", actor, f"desk {office_name} handed to {new_username.strip().lower()}")
    temp = create_login(client, username=new_username, role="office_officer", department=department, office_name=office_name, actor=actor, dept_id=dept_id, label=label, taken=taken)
    return temp, old


def change_password(client: Any, username: str, old_password: str, new_password: str) -> None:
    """The holder chooses their own password (forced after a temporary one). Needs the current password."""
    record = _one(client, username)
    if not record or not record.get("active") or not accounts.verify_password(old_password or "", record):
        raise DeskAccessError("The current password is not right.")
    if len(new_password or "") < MIN_PASSWORD:
        raise DeskAccessError(f"The new password must be at least {MIN_PASSWORD} characters.")
    if new_password == old_password or new_password.lower() == record["username"].lower():
        raise DeskAccessError("Choose a password different from the current one and from the username.")
    client.table(ACCOUNTS).update({**accounts.hash_password(new_password), "must_change": False, "updated_at": _now()}).eq("username", record["username"]).execute()
    record_event(client, record["username"], "password_changed", record["username"])


def touch_login(client: Any, username: str) -> None:
    """Remember when a login was last used (so a desk with a login nobody has used for months stands out). Best effort."""
    try:
        client.table(ACCOUNTS).update({"last_login_at": _now()}).eq("username", username.strip().lower()).execute()
    except Exception:  # noqa: BLE001
        logger.warning("last login not recorded")
