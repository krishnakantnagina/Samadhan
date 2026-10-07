"""A citizen's right to have their data removed (privacy notice, audit H2).

`plan()` lists what would go; `erase()` does it. What "erase" means here, and what it deliberately keeps:
  * REMOVED: the user row (the phone number), every saved login and any unfinished login challenge for that number, and the voice recordings (audio files) of
    that citizen's complaints, both on the tickets and on the chat messages;
  * UNLINKED: tickets stay (they are the government's record of a complaint and the officers' work), but `user_id` is cleared, so nothing connects them to a phone
    number any more;
  * KEPT: the written complaint text and ticket fields. They describe a public-service problem, not the person; if they name someone, that is a separate
    redaction decision for the project team.
Run it from backend/scripts/delete_citizen_data.py (dry run unless --yes). It needs the service key, like the server.
"""

from dataclasses import dataclass, field
from typing import Any

from app import auth


@dataclass
class ErasePlan:
    user_id: str
    complaint_ids: list[str] = field(default_factory=list)
    session_ids: list[str] = field(default_factory=list)
    audio_paths: list[str] = field(default_factory=list)
    login_sessions: int = 0


def _rows(query: Any) -> list[dict[str, Any]]:
    return query.execute().data or []


def plan(client: Any, raw_phone: str) -> ErasePlan | None:
    """What would be removed for this phone number, or None when nobody is registered with it."""
    phone = auth.normalise_phone(raw_phone)
    users = _rows(client.table("users").select("id").eq("phone", phone))
    if not users:
        return None
    user_id = str(users[0]["id"])
    result = ErasePlan(user_id=user_id)
    for t in _rows(client.table("tickets").select("complaint_id,session_id,audio_path").eq("user_id", user_id)):
        result.complaint_ids.append(t["complaint_id"])
        if t.get("session_id"):
            result.session_ids.append(str(t["session_id"]))
        if t.get("audio_path"):
            result.audio_paths.append(t["audio_path"])
    for sid in dict.fromkeys(result.session_ids):
        for m in _rows(client.table("messages").select("audio_path").eq("session_id", sid)):
            if m.get("audio_path") and m["audio_path"] not in result.audio_paths:
                result.audio_paths.append(m["audio_path"])
    result.login_sessions = len(_rows(client.table("auth_sessions").select("id").eq("user_id", user_id)))
    return result


def erase(client: Any, raw_phone: str) -> ErasePlan | None:
    """Do it. Returns what was removed (None when nobody is registered). Order matters: tickets are unlinked before the user row goes (foreign key)."""
    found = plan(client, raw_phone)
    if found is None:
        return None
    phone = auth.normalise_phone(raw_phone)
    if found.audio_paths:
        client.storage.from_("audio").remove(found.audio_paths)
        for sid in dict.fromkeys(found.session_ids):
            client.table("messages").update({"audio_path": None}).eq("session_id", sid).execute()
        client.table("tickets").update({"audio_path": None}).eq("user_id", found.user_id).execute()
    client.table("tickets").update({"user_id": None}).eq("user_id", found.user_id).execute()
    client.table("auth_sessions").delete().eq("user_id", found.user_id).execute()
    client.table("auth_challenges").delete().eq("phone", phone).execute()
    client.table("users").delete().eq("id", found.user_id).execute()
    return found
