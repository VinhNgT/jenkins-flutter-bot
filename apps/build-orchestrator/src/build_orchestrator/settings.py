"""Build orchestrator settings — resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Immutable application settings resolved once at startup.

    Env vars:
        FILE_MANAGER_URL  — Base URL of the file-manager service
        SELF_URL          — This service's own URL (for webhook callbacks)
        BUILD_DATA_PATH   — Directory for build state persistence
        CONFIG_PATH       — Path to orchestrator config JSON file
    """

    file_manager_url: str
    self_url: str
    build_data_path: Path
    config_path: Path | None

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve settings from environment variables."""
        config_val = os.environ.get("CONFIG_PATH")
        return cls(
            file_manager_url=os.environ.get(
                "FILE_MANAGER_URL", "http://file-manager:9092"
            ),
            self_url=os.environ.get("SELF_URL", "http://build-orchestrator:9010"),
            build_data_path=Path(
                os.environ.get("BUILD_DATA_PATH", "data/builds")
            ),
            config_path=Path(config_val) if config_val else None,
        )
