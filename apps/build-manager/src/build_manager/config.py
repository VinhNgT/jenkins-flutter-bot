"""Typed frozen config dataclass for the build manager."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import BUILD_FIELDS, BUILD_INFRA, resolve_fields


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
        all_fields = BUILD_FIELDS + BUILD_INFRA
        values: dict[str, Any] = resolve_fields(all_fields, config_path)
        return cls(**{f.attr: values.get(f.attr, "") for f in all_fields})
