"""Project configuration resolved from the shared project schema."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from config_schema import FieldDef, resolve_fields

# Project fields inlined — previously from stack-manager lib.
# stack-manager (service) also declares these; they must stay in sync.
PROJECT_FIELDS: tuple[FieldDef, ...] = (
    FieldDef(
        key="project.github_url",
        env_var="PROJECT_GITHUB_URL",
        attr="github_url",
        label="GitHub URL",
        group="Repository",
        description="Link to the project's GitHub repository",
    ),
)


@dataclass(frozen=True)
class ProjectConfig:
    """Project-wide configuration resolved from project.json, env, and defaults."""

    github_url: str

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> ProjectConfig:
        """Build project config with priority: file > env > .env > defaults.

        If *config_path* is not provided, reads PROJECT_CONFIG_PATH from the
        environment (set by docker-compose via the project-config volume mount).
        """
        if config_path is None:
            raw = os.environ.get("PROJECT_CONFIG_PATH")
            config_path = Path(raw) if raw else None
        values = resolve_fields(PROJECT_FIELDS, config_path)
        return cls(**values)

