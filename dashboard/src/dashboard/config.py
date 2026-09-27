"""S13 -- Dashboard env config. Spec: docs/specs/S13-dashboard-auth-list.md.

Same _require pattern as backend/app/config.py, duplicated on purpose -- separate uv projects,
no shared package between backend/ and dashboard/.
"""

import os
from dataclasses import dataclass


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


@dataclass(frozen=True)
class DashboardConfig:
    supabase_url: str
    supabase_service_key: str
    dashboard_password: str


def get_dashboard_config() -> DashboardConfig:
    """SUPABASE_URL, SUPABASE_SERVICE_KEY, DASHBOARD_PASSWORD -- all required, fail fast."""
    return DashboardConfig(
        supabase_url=_require("SUPABASE_URL"),
        supabase_service_key=_require("SUPABASE_SERVICE_KEY"),
        dashboard_password=_require("DASHBOARD_PASSWORD"),
    )
