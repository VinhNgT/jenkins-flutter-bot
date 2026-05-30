"""Storage manager — file-manager lifecycle and backend initialisation.

Follows the same manager pattern as other services — mutable state
attached to ``app.state``, frozen config resolved on demand.

The ``STORAGE_BACKEND`` environment variable selects which backend to
instantiate: ``"google_drive"`` (default) or ``"ephemeral"``.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from config_core import format_validation_error, resolve_config_path
from pydantic import ValidationError

from .backends.ephemeral import EphemeralBackend
from .backends.google_drive import GoogleDriveBackend
from .backends.log_only import LogOnlyBackend
from .build_log import BuildLog
from .config import StorageSettings, _DEFAULT_CONFIG_PATH
from .storage import StorageBackend

logger = logging.getLogger(__name__)


class StartupError(Exception):
    """Raised when the storage manager fails to start."""


def _resolve_backend_type() -> str:
    """Read the storage backend type from the environment.

    Returns ``"google_drive"`` or ``"ephemeral"``.
    """
    raw = os.environ.get("STORAGE_BACKEND", "google_drive").strip().lower()
    if raw not in ("google_drive", "ephemeral", "log_only"):
        logger.warning(
            "Unknown STORAGE_BACKEND=%r, falling back to 'google_drive'", raw,
        )
        return "google_drive"
    return raw


class StorageManager:
    """Manages the storage backend lifecycle and configuration.

    The backend type is determined by the ``STORAGE_BACKEND`` environment
    variable. In ``"ephemeral"`` mode, files are stored in memory and
    Drive credentials are not required. In ``"google_drive"`` mode
    (default), the manager initialises a ``GoogleDriveBackend`` with
    the resolved config values.

    For testing, pass a ``backend`` override to bypass auto-creation.
    """

    def __init__(
        self,
        *,
        backend: StorageBackend | None = None,
    ) -> None:
        self._config: StorageSettings | None = None
        self._backend: StorageBackend | None = backend
        self._test_backend = backend
        self._build_log: BuildLog | None = None
        self._last_error: str | None = None
        self._started_at: float | None = None
        self._backend_type = _resolve_backend_type()

    @property
    def config(self) -> StorageSettings | None:
        return self._config

    @property
    def backend(self) -> StorageBackend | None:
        return self._backend

    @property
    def backend_type(self) -> str:
        """Return the configured backend type (``"google_drive"`` or ``"ephemeral"``)."""
        return self._backend_type

    @property
    def build_log(self) -> BuildLog | None:
        """Return the build log, or None if the manager hasn't started."""
        return self._build_log

    @property
    def google_drive_backend(self) -> GoogleDriveBackend | None:
        """Return the backend only if it is a ``GoogleDriveBackend``.

        Used by OAuth routes that require Drive-specific methods.
        """
        return self._backend if isinstance(self._backend, GoogleDriveBackend) else None

    @property
    def ephemeral_backend(self) -> EphemeralBackend | None:
        """Return the backend only if it is an ``EphemeralBackend``.

        Used by the download endpoint to retrieve stored files.
        """
        return self._backend if isinstance(self._backend, EphemeralBackend) else None

    @property
    def running(self) -> bool:
        return self._backend is not None

    def _token_path(self) -> Path:
        return resolve_config_path(_DEFAULT_CONFIG_PATH).parent / "oauth.json"

    async def start(self, config: StorageSettings | None = None) -> None:
        """Resolve config and initialise the storage backend."""
        try:
            self._config = config or StorageSettings.load()
        except (ValueError, ValidationError) as e:
            self._last_error = str(e)
            raise StartupError(str(e)) from e

        # Test override — use the injected backend as-is
        if self._test_backend is not None:
            self._backend = self._test_backend
        elif self._backend_type == "ephemeral":
            self._backend = EphemeralBackend()
        elif self._backend_type == "log_only":
            self._backend = LogOnlyBackend()
        else:
            self._backend = GoogleDriveBackend(
                self._token_path(),
                client_id=self._config.drive_client_id,
                client_secret=self._config.drive_client_secret,
                folder_name=self._config.drive_folder_name,
            )

        self._build_log = BuildLog(
            data_dir=resolve_config_path(_DEFAULT_CONFIG_PATH).parent,
            max_records=self._config.max_recent_builds,
            persistent=(self._backend_type != "ephemeral"),
            filename=f"build_log_{self._backend_type}.json",
        )

        # Reconcile the build log against actual Drive contents at startup.
        # This removes stale log entries (file deleted externally) and purges
        # orphaned Drive files (uploaded but never recorded, or outlived their
        # log entry due to a crash).
        if self._backend_type == "google_drive" and isinstance(self._backend, GoogleDriveBackend):
            await self._reconcile_drive_index(self._backend, self._build_log)

        self._last_error = None
        self._started_at = time.time()
        logger.info("StorageManager started (backend=%s)", self._backend_type)

    async def stop(self) -> None:
        """Shut down the storage backend."""
        self._backend = None
        self._build_log = None
        self._config = None
        self._started_at = None
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
        result: dict[str, Any] = {
            "configured": config_error is None,
            "running": self.running,
            "last_error": self._last_error,
            "config_error": config_error,
            "backend_type": self._backend_type,
        }
        if self._started_at is not None:
            result["started_at"] = self._started_at
        return result

    # ------------------------------------------------------------------
    # Drive index reconciliation
    # ------------------------------------------------------------------

    @staticmethod
    async def _reconcile_drive_index(
        backend: GoogleDriveBackend,
        build_log: BuildLog,
    ) -> None:
        """Reconcile the local build log against actual Google Drive contents.

        - **Stale log entries** (file_id deleted externally) are removed.
        - **Recovered orphans** (not tracked locally) are added to the log.
        - **Evicted records** (exceeding max_records) are removed from Drive.

        Best-effort: if Drive is not connected (tokens missing/expired),
        reconciliation is skipped silently so it doesn't block startup.
        """
        try:
            drive_files = await backend.list_files()
        except RuntimeError:
            logger.info("Drive not connected — skipping index reconciliation")
            return
        except Exception:
            logger.exception("Failed to list Drive files — skipping reconciliation")
            return

        stale, evicted = build_log.reconcile(drive_files)

        if stale:
            logger.info(
                "Reconciliation: removed %d stale log entries (files deleted externally): %s",
                len(stale),
                [r.request_id for r in stale],
            )

        for record in evicted:
            if not record.file_id:
                continue
            try:
                await backend.delete(record.file_id)
                logger.info(
                    "Reconciliation: evicted and deleted excess Drive file %s (%s)",
                    record.branch,
                    record.file_id,
                )
            except Exception:
                logger.exception(
                    "Reconciliation: failed to delete evicted file %s (%s)",
                    record.branch,
                    record.file_id,
                )

        if not stale and not evicted:
            logger.info("Reconciliation: build log and Drive index are in sync")

