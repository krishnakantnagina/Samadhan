"""S31 -- Citizen identity: phone registration, swappable verification, saved login.

Why: a complaint needs an owner. The registered phone lets the officer who handles the ticket call the citizen back, lets the citizen see their own
complaints later, and (future) lets WhatsApp / call channels reuse the same user without asking for a PIN again.

Swap points (everything else stays the same when real verification arrives):
  * IdentityProvider: `start()` sends a code, `verify()` checks it. DemoProvider accepts any phone and the fixed PIN 5555. A real SMS OTP provider is one new
    class registered in PROVIDERS and selected with AUTH_PROVIDER=<name>; an Aadhaar-linked provider would return a *reference key*, never the number.
  * AuthStore: where users, challenges and login sessions live (Supabase in production, in memory for tests/dev).
  * Channel identities (WhatsApp number, call caller id) skip verification: `user_for_channel(identifier, verified_by="whatsapp")`.

Saved login: a random token; only its SHA-256 is stored. Sliding idle expiry (default 30 days) with an absolute maximum (default 90 days); after that the
citizen logs in again. This is separate from the 30-minute chat-conversation timeout (S20).

Safety: attempt limits per challenge and per phone; the demo PIN works ONLY when AUTH_PROVIDER=demo, and refuses to run on a production host
(RAILWAY_ENVIRONMENT=production, or RENDER=true on Render) unless AUTH_DEMO_IN_PRODUCTION=1 is set on purpose; PIN, code and token are never logged.
Disabled unless AUTH_PROVIDER is set. Registration is required only for filing a complaint (AUTH_REQUIRED=1); enquiries and status checks stay open.
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Protocol

from app import schemas

logger = logging.getLogger(__name__)

DEMO_PIN = "5555"
PHONE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian mobile numbers start with 6, 7, 8 or 9


class AuthError(Exception):
    """A login problem with the API error code the route should return."""

    def __init__(self, code: schemas.ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class AuthDisabled(RuntimeError):
    """AUTH_PROVIDER is not set (or is unsafe here): login endpoints answer 503, enquiries are unaffected."""


@dataclass(frozen=True)
class User:
    id: str
    phone: str  # E.164, e.g. +919876543210
    verified_by: str  # demo | sms_otp | whatsapp | caller_id | ...


@dataclass(frozen=True)
class Identity:
    identifier: str
    verified_by: str


def normalise_phone(raw: str) -> str:
    """'98765 43210', '+91 98765-43210', '09876543210' -> '+919876543210'. Anything else is an error."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not PHONE_RE.match(digits):
        raise AuthError(schemas.ErrorCode.INVALID_INPUT, "Enter a 10 digit mobile number.")
    return f"+91{digits}"


def mask_phone(phone: str) -> str:
    return f"{phone[:3]} {'•' * 6}{phone[-4:]}" if len(phone) >= 8 else "•••"


# --- providers (the swap point for real verification) --------------------------------------------------------


class IdentityProvider(Protocol):
    name: str
    hint: str | None  # shown on the login screen (the demo says what the PIN is); None for real providers

    def start(self, phone: str) -> None: ...

    def verify(self, phone: str, code: str) -> Identity | None: ...


class DemoProvider:
    """DEMO ONLY. Any phone number is accepted and the PIN is fixed at 5555."""

    name = "demo"
    hint = "Demo: enter PIN 5555"

    def start(self, phone: str) -> None:
        return None  # nothing to send

    def verify(self, phone: str, code: str) -> Identity | None:
        return Identity(phone, "demo") if hmac.compare_digest(code.encode(), DEMO_PIN.encode()) else None


PROVIDERS: dict[str, Callable[[], IdentityProvider]] = {"demo": DemoProvider}  # add "sms": SmsOtpProvider here when real OTP arrives


# --- stores ---------------------------------------------------------------------------------------------------


class AuthStore(Protocol):
    def upsert_user(self, phone: str, verified_by: str) -> User: ...
    def get_user(self, user_id: str) -> User | None: ...
    def create_challenge(self, phone: str, provider: str, expires_at: datetime) -> str: ...
    def get_challenge(self, challenge_id: str) -> dict[str, Any] | None: ...
    def bump_attempts(self, challenge_id: str) -> None: ...
    def delete_challenge(self, challenge_id: str) -> None: ...
    def delete_expired_challenges(self, before: datetime) -> None: ...
    def count_challenges_since(self, phone: str, since: datetime) -> int: ...
    def create_session(self, user_id: str, token_hash: str, idle_expires_at: datetime, absolute_expires_at: datetime) -> str: ...
    def get_session(self, token_hash: str) -> dict[str, Any] | None: ...
    def touch_session(self, session_id: str, idle_expires_at: datetime) -> None: ...
    def revoke_session(self, session_id: str) -> None: ...


class MemoryAuthStore:
    """In-process store for tests and local development. Not shared between processes."""

    def __init__(self, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._now = now  # injectable so tests can drive time
        self.users: dict[str, User] = {}
        self.challenges: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self._n = 0

    def _id(self) -> str:
        self._n += 1
        return f"{self._n:08d}-0000-4000-8000-000000000000"

    def upsert_user(self, phone: str, verified_by: str) -> User:
        found = next((u for u in self.users.values() if u.phone == phone), None)
        if found:
            return found
        user = User(self._id(), phone, verified_by)
        self.users[user.id] = user
        return user

    def get_user(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    def create_challenge(self, phone: str, provider: str, expires_at: datetime) -> str:
        cid = self._id()
        self.challenges[cid] = {"id": cid, "phone": phone, "provider": provider, "attempts": 0, "expires_at": expires_at, "created_at": self._now()}
        return cid

    def get_challenge(self, challenge_id: str) -> dict[str, Any] | None:
        return self.challenges.get(challenge_id)

    def bump_attempts(self, challenge_id: str) -> None:
        self.challenges[challenge_id]["attempts"] += 1

    def delete_challenge(self, challenge_id: str) -> None:
        self.challenges.pop(challenge_id, None)

    def delete_expired_challenges(self, before: datetime) -> None:
        for cid in [c for c, v in self.challenges.items() if v["expires_at"] < before]:
            del self.challenges[cid]

    def count_challenges_since(self, phone: str, since: datetime) -> int:
        return sum(1 for c in self.challenges.values() if c["phone"] == phone and c["created_at"] >= since)

    def create_session(self, user_id: str, token_hash: str, idle_expires_at: datetime, absolute_expires_at: datetime) -> str:
        sid = self._id()
        self.sessions[token_hash] = {"id": sid, "user_id": user_id, "idle_expires_at": idle_expires_at, "absolute_expires_at": absolute_expires_at, "revoked": False}
        return sid

    def get_session(self, token_hash: str) -> dict[str, Any] | None:
        return self.sessions.get(token_hash)

    def touch_session(self, session_id: str, idle_expires_at: datetime) -> None:
        for s in self.sessions.values():
            if s["id"] == session_id:
                s["idle_expires_at"] = idle_expires_at

    def revoke_session(self, session_id: str) -> None:
        for s in self.sessions.values():
            if s["id"] == session_id:
                s["revoked"] = True


def _dt(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


class SupabaseAuthStore:
    """Production store: tables users, auth_challenges, auth_sessions (database/migrations/002). Service key only, RLS on, no public policies."""

    def __init__(self, client: Any) -> None:
        self.c = client

    def upsert_user(self, phone: str, verified_by: str) -> User:
        now = datetime.now(UTC).isoformat()
        existing = self.c.table("users").select("id,phone,verified_by").eq("phone", phone).execute().data
        if existing:
            self.c.table("users").update({"last_seen_at": now}).eq("id", existing[0]["id"]).execute()
            r = existing[0]
        else:
            r = self.c.table("users").insert({"phone": phone, "verified_by": verified_by, "last_seen_at": now}).execute().data[0]
        return User(str(r["id"]), r["phone"], r["verified_by"])

    def get_user(self, user_id: str) -> User | None:
        rows = self.c.table("users").select("id,phone,verified_by").eq("id", user_id).execute().data
        return User(str(rows[0]["id"]), rows[0]["phone"], rows[0]["verified_by"]) if rows else None

    def create_challenge(self, phone: str, provider: str, expires_at: datetime) -> str:
        return str(self.c.table("auth_challenges").insert({"phone": phone, "provider": provider, "expires_at": expires_at.isoformat()}).execute().data[0]["id"])

    def get_challenge(self, challenge_id: str) -> dict[str, Any] | None:
        rows = self.c.table("auth_challenges").select("*").eq("id", challenge_id).execute().data
        return {**rows[0], "expires_at": _dt(rows[0]["expires_at"])} if rows else None

    def bump_attempts(self, challenge_id: str) -> None:
        row = self.get_challenge(challenge_id)
        if row:
            self.c.table("auth_challenges").update({"attempts": int(row["attempts"]) + 1}).eq("id", challenge_id).execute()

    def delete_challenge(self, challenge_id: str) -> None:
        self.c.table("auth_challenges").delete().eq("id", challenge_id).execute()

    def delete_expired_challenges(self, before: datetime) -> None:
        self.c.table("auth_challenges").delete().lt("expires_at", before.isoformat()).execute()

    def count_challenges_since(self, phone: str, since: datetime) -> int:
        return int(self.c.table("auth_challenges").select("id", count="exact").eq("phone", phone).gte("created_at", since.isoformat()).execute().count or 0)

    def create_session(self, user_id: str, token_hash: str, idle_expires_at: datetime, absolute_expires_at: datetime) -> str:
        return str(self.c.table("auth_sessions").insert({"user_id": user_id, "token_hash": token_hash, "idle_expires_at": idle_expires_at.isoformat(),
                                                         "absolute_expires_at": absolute_expires_at.isoformat()}).execute().data[0]["id"])

    def get_session(self, token_hash: str) -> dict[str, Any] | None:
        rows = self.c.table("auth_sessions").select("*").eq("token_hash", token_hash).execute().data
        if not rows:
            return None
        r = rows[0]
        return {**r, "user_id": str(r["user_id"]), "idle_expires_at": _dt(r["idle_expires_at"]), "absolute_expires_at": _dt(r["absolute_expires_at"])}

    def touch_session(self, session_id: str, idle_expires_at: datetime) -> None:
        self.c.table("auth_sessions").update({"last_seen_at": datetime.now(UTC).isoformat(), "idle_expires_at": idle_expires_at.isoformat()}).eq("id", session_id).execute()

    def revoke_session(self, session_id: str) -> None:
        self.c.table("auth_sessions").update({"revoked": True}).eq("id", session_id).execute()


# --- the service -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StartResult:
    challenge_id: str
    provider: str
    hint: str | None


@dataclass(frozen=True)
class LoginResult:
    token: str
    expires_at: datetime
    user: User


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, store: AuthStore, provider: IdentityProvider, *, now: Callable[[], datetime] = lambda: datetime.now(UTC), idle_days: int = 30,
                 max_days: int = 90, challenge_minutes: int = 10, max_attempts: int = 5, max_starts_per_hour: int = 5) -> None:
        self.store, self.provider, self._now = store, provider, now
        self.idle, self.absolute = timedelta(days=idle_days), timedelta(days=max_days)
        self.challenge_ttl, self.max_attempts, self.max_starts = timedelta(minutes=challenge_minutes), max_attempts, max_starts_per_hour

    def start(self, raw_phone: str) -> StartResult:
        phone = normalise_phone(raw_phone)
        now = self._now()
        if secrets.randbelow(20) == 0:  # now and then: forget challenges that expired a day ago (nobody finished them), so the table cannot grow for ever
            try:
                self.store.delete_expired_challenges(now - timedelta(days=1))
            except Exception:  # noqa: BLE001 -- housekeeping must never block a login
                logger.warning("auth: could not purge expired challenges")
        if self.store.count_challenges_since(phone, now - timedelta(hours=1)) >= self.max_starts:
            raise AuthError(schemas.ErrorCode.AUTH_RATE_LIMITED, "Too many attempts. Try again later.")
        self.provider.start(phone)
        return StartResult(self.store.create_challenge(phone, self.provider.name, now + self.challenge_ttl), self.provider.name, self.provider.hint)

    def verify(self, challenge_id: str, code: str) -> LoginResult:
        challenge = self.store.get_challenge(challenge_id)
        now = self._now()
        if challenge is None or challenge["expires_at"] < now:
            raise AuthError(schemas.ErrorCode.AUTH_INVALID_CODE, "The code has expired. Start again.")
        if int(challenge["attempts"]) >= self.max_attempts:
            self.store.delete_challenge(challenge_id)
            raise AuthError(schemas.ErrorCode.AUTH_RATE_LIMITED, "Too many wrong codes. Start again.")
        identity = self.provider.verify(challenge["phone"], (code or "").strip())
        if identity is None:
            self.store.bump_attempts(challenge_id)
            raise AuthError(schemas.ErrorCode.AUTH_INVALID_CODE, "Wrong code.")
        self.store.delete_challenge(challenge_id)
        user = self.store.upsert_user(identity.identifier, identity.verified_by)
        token = secrets.token_urlsafe(32)
        absolute = now + self.absolute
        self.store.create_session(user.id, hash_token(token), min(now + self.idle, absolute), absolute)
        return LoginResult(token, min(now + self.idle, absolute), user)

    def user_for_token(self, token: str | None) -> User | None:
        """The logged-in user for this token, extending the idle window; None when missing, expired, revoked or unknown."""
        if not token:
            return None
        session = self.store.get_session(hash_token(token))
        now = self._now()
        if session is None or session["revoked"] or now > session["idle_expires_at"] or now > session["absolute_expires_at"]:
            return None
        self.store.touch_session(session["id"], min(now + self.idle, session["absolute_expires_at"]))
        return self.store.get_user(session["user_id"])

    def expires_at(self, token: str) -> datetime | None:
        session = self.store.get_session(hash_token(token))
        return session["idle_expires_at"] if session else None

    def logout(self, token: str | None) -> None:
        session = self.store.get_session(hash_token(token)) if token else None
        if session:
            self.store.revoke_session(session["id"])

    def user_for_channel(self, identifier: str, verified_by: str) -> User:
        """WhatsApp / phone-call identities arrive already verified by the channel: same user table, no PIN, no token."""
        return self.store.upsert_user(normalise_phone(identifier), verified_by)


# --- configuration ---------------------------------------------------------------------------------------------


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def required() -> bool:
    """Registration is required to file a complaint (AUTH_REQUIRED=1 and a provider configured). Misconfigured = fail open: complaints are never blocked by auth setup."""
    if not _truthy("AUTH_REQUIRED"):
        return False
    if not os.environ.get("AUTH_PROVIDER", "").strip():
        logger.error("AUTH_REQUIRED is on but AUTH_PROVIDER is not set: registration is NOT enforced")
        return False
    return True


@lru_cache
def get_service() -> AuthService:
    name = os.environ.get("AUTH_PROVIDER", "").strip().lower()
    if not name:
        raise AuthDisabled("AUTH_PROVIDER is not set")
    if name not in PROVIDERS:
        raise AuthDisabled(f"unknown AUTH_PROVIDER {name!r}")
    if name == "demo" and (os.environ.get("RAILWAY_ENVIRONMENT", "").lower() == "production" or _truthy("RENDER")) and not _truthy("AUTH_DEMO_IN_PRODUCTION"):
        raise AuthDisabled("the demo PIN is refused on a production host (set AUTH_DEMO_IN_PRODUCTION=1 only if you mean it)")
    if name == "demo":
        logger.warning("DEMO AUTH ACTIVE: any phone number with PIN 5555 can log in. Never use this for real citizens.")
    store: AuthStore
    if os.environ.get("AUTH_STORE", "").strip().lower() == "memory":  # explicit opt-in for local demos (migration 002 not applied): logins are lost on restart
        logger.warning("auth: AUTH_STORE=memory, logins are kept in memory only (and the phone is NOT linked to tickets without migration 002)")
        store = MemoryAuthStore()
    else:
        try:
            from app.db import get_client

            store = SupabaseAuthStore(get_client())
        except Exception:  # noqa: BLE001 -- no database configured (local dev): keep logins in memory
            logger.warning("auth: no database client, using the in-memory store (logins are lost on restart)")
            store = MemoryAuthStore()
    return AuthService(store, PROVIDERS[name](), idle_days=int(os.environ.get("AUTH_IDLE_DAYS", "30")), max_days=int(os.environ.get("AUTH_MAX_DAYS", "90")))


def token_from_header(authorization: str | None) -> str | None:
    """'Bearer abc' -> 'abc'; anything else -> None."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def user_from_header(authorization: str | None) -> User | None:
    """The logged-in citizen for this request, or None (no header, bad/expired token, or auth disabled). Never raises."""
    token = token_from_header(authorization)
    if not token:
        return None
    try:
        return get_service().user_for_token(token)
    except AuthDisabled:
        return None
    except Exception:  # noqa: BLE001 -- a store hiccup must not break the chat: treat as not logged in
        logger.warning("auth lookup failed; treating the request as anonymous")
        return None
