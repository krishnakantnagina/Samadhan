"""S06 -- shared Supabase client factory. Spec: docs/specs/S06-session-manager.md, T27 (S13-hardening).

One client per process, reused by app/session.py, app/jurisdiction.py, app/ticketing.py, and
app/voice.py's storage upload.

T27: supabase-py's own defaults are dangerously long for a citizen-facing request --
postgrest_client_timeout defaults to 120s, storage_client_timeout to 20s. A DB hiccup would hang a
request for up to two minutes instead of failing fast into the existing 500 INTERNAL_ERROR path
(S06 RULES 6). Explicit, sane timeouts here, matching the same order of magnitude as every other
external call's budget (Groq/Gemini ~6s, Sarvam/Groq Whisper ~8s, PROJECT.md section 7/S04 section 5).

Either of us can change this file; if you do, tell the other.
"""

from functools import lru_cache

from supabase import Client, ClientOptions, create_client

from app.config import get_supabase_config

POSTGREST_TIMEOUT_SECONDS = 10.0
STORAGE_TIMEOUT_SECONDS = 15.0  # audio uploads are bigger payloads than a table read/write


@lru_cache
def get_client() -> Client:
    config = get_supabase_config()
    options = ClientOptions(
        postgrest_client_timeout=POSTGREST_TIMEOUT_SECONDS,
        storage_client_timeout=STORAGE_TIMEOUT_SECONDS,
    )
    return create_client(config.url, config.service_key, options=options)
