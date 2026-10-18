"""Runtime configuration, read from ATC_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    workspace_slug: str = "nakomis"
    max_points: int = 100
    reconcile_seconds: int = 300
    plane_web_url: str = "https://plane.home.nakomis.com"
    static_dir: Path | None = None

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from the environment; ATC_DATABASE_URL is required (KeyError if absent)."""
        env = os.environ
        defaults = cls(database_url="")
        static_dir = env.get("ATC_STATIC_DIR")
        return cls(
            database_url=env["ATC_DATABASE_URL"],
            workspace_slug=env.get("ATC_WORKSPACE_SLUG", defaults.workspace_slug),
            max_points=int(env.get("ATC_MAX_POINTS", defaults.max_points)),
            reconcile_seconds=int(env.get("ATC_RECONCILE_SECONDS", defaults.reconcile_seconds)),
            plane_web_url=env.get("ATC_PLANE_WEB_URL", defaults.plane_web_url),
            static_dir=Path(static_dir) if static_dir else None,
        )
