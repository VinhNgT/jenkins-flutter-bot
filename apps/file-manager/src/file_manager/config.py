"""Storage configuration resolved from declarative schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import registry

# Default config file path inside the container.  Can be overridden via the
# CONFIG_PATH environment variable for local development outside Docker.
_DEFAULT_CONFIG_PATH = Path("/app/data/storage.json")


@dataclass(frozen=True)
class StorageConfig:
    """Storage configuration resolved from config file, env, and defaults."""

    # OAuth credentials
    drive_client_id: str
    drive_client_secret: str

    # Storage settings
    drive_folder_name: str

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> StorageConfig:
        """Build config with priority: file > env > .env > defaults."""
        values = registry.resolve(config_path or _DEFAULT_CONFIG_PATH)
        return cls(**values)
