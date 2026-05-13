"""Typed frozen config dataclass for the build manager."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import registry


@dataclass(frozen=True)
class BuildConfig:
    """Resolved build manager configuration.

    Use ``BuildConfig.resolve()`` to build an instance from the
    standard config precedence chain (JSON → env → defaults).
    """

    jenkins_url: str
    jenkins_user: str
    jenkins_api_token: str
    jenkins_job_name: str
    jenkins_credentials_id: str
    git_repo_url: str
    # Infra
    file_manager_url: str
    self_url: str

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> BuildConfig:
        """Resolve config from all sources."""
        values = registry.resolve(config_path)
        return cls(**values)
