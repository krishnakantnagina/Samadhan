"""S13 -- Supabase client factory. Spec: docs/specs/S13-dashboard-auth-list.md.

Service key, not anon key (PROJECT.md section 8: dashboard is server-side, same posture as the
backend core). Mirrors backend/app/db.py's shape -- its own module, separate uv project.
"""

from functools import lru_cache

from supabase import Client, create_client

from dashboard.config import get_dashboard_config


@lru_cache
def get_client() -> Client:
    config = get_dashboard_config()
    return create_client(config.supabase_url, config.supabase_service_key)
