"""S06 -- shared Supabase client factory. Spec: docs/specs/S06-session-manager.md.

One client per process, reused by app/session.py and (later) T16/T17. Either of us can change this
file; if you do, tell the other.
"""

from functools import lru_cache

from supabase import Client, create_client

from app.config import get_supabase_config


@lru_cache
def get_client() -> Client:
    config = get_supabase_config()
    return create_client(config.url, config.service_key)
