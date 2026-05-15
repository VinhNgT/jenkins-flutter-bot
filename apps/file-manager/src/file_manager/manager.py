"""Storage manager — file-manager lifecycle and backend initialisation.

Follows the same manager pattern as other services — mutable state
attached to ``app.state``, frozen config resolved on demand.
"""

from __future__ import annotations

import logging
from typing import Any

from config_core import format_validation_error
from pydantic import ValidationError

from .backends.google_drive import GoogleDriveBackend
from .config import StorageSettings, _DEFAULT_CONFIG_PATH

logger = logging.getLogger(__name__)


class StartupError(Exception):
    """Raised when the storage manager fails to start."""


class StorageManager:
    """Manages the storage backend lifecycle and configuration."""

    def __init__(self) -> None:
        self._config: StorageSettings | None = None
        self._backend: GoogleDriveBackend | None = None
        self._last_error: str | None = None

    @property
    def config(self) -> StorageSettings | None:
        return self._config

    @property
    def backend(self) -> GoogleDriveBackend | None:
        return self._backend

    @property
    def running(self) -> bool:
        return self._backend is not None

    def _token_path(self):
        return _DEFAULT_CONFIG_PATH.parent / "oauth.json"

    async def start(self) -> None:
        """Resolve config and initialise the storage backend."""
        try:
            self._config = StorageSettings.load()
        except (ValueError, ValidationError) as e:
            self._last_error = str(e)
            raise StartupError(str(e)) from e

        self._backend = GoogleDriveBackend(self._token_path())
        self._last_error = None
        logger.info("StorageManager started")

    async def stop(self) -> None:
        """Shut down the storage backend."""
        self._backend = None
        self._config = None
        logger.info("StorageManager stopped")

    async def restart(self) -> None:
        """Stop and re-start with fresh config."""
        await self.stop()
        await self.start()

    def status(self) -> dict[str, Any]:
        """Return the current storage manager status."""
        config_error: str | None = None
        try:
            StorageSettings.load()
        except Exception as exc:
            config_error = format_validation_error(exc)
        return {
            "configured": config_error is None,
            "running": self.running,
            "last_error": self._last_error,
            "config_error": config_error,
        }
