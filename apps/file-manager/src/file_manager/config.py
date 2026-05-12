"""Storage configuration resolved from declarative schema."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .schema import STORAGE_FIELDS, STORAGE_INFRA, resolve_fields


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
        if config_path is None and os.environ.get("CONFIG_PATH"):
            config_path = Path(os.environ["CONFIG_PATH"])
        values = resolve_fields(STORAGE_FIELDS + STORAGE_INFRA, config_path)
        return cls(**values)
