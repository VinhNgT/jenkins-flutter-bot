"""Build manager settings — resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Default paths inside the container. Both can be overridden via environment
# variables for local development outside Docker.
_DEFAULT_CONFIG_PATH = Path("/app/data/builds.json")
_DEFAULT_BUILD_DATA_PATH = Path("/app/data")


@dataclass(frozen=True)
class Settings:
    """Immutable application settings resolved once at startup.

    Env vars (all optional — sensible container defaults are hardcoded):
        FILE_MANAGER_URL  — Base URL of the file-manager service
        SELF_URL          — This service's own URL (for webhook callbacks)
        BUILD_DATA_PATH   — Directory for build state persistence
        CONFIG_PATH       — Path to build manager config JSON file
    """

    file_manager_url: str
    self_url: str
    build_data_path: Path
    config_path: Path

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve settings from environment variables."""
        config_val = os.environ.get("CONFIG_PATH")
        data_val = os.environ.get("BUILD_DATA_PATH")
        return cls(
            file_manager_url=os.environ.get(
                "FILE_MANAGER_URL", "http://file-manager:9092"
            ),
            self_url=os.environ.get("SELF_URL", "http://build-manager:9010"),
            build_data_path=Path(data_val) if data_val else _DEFAULT_BUILD_DATA_PATH,
            config_path=Path(config_val) if config_val else _DEFAULT_CONFIG_PATH,
        )
