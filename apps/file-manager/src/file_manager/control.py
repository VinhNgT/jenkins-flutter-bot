"""Storage manager and /control/* routes for file-manager."""

from __future__ import annotations

import logging
from typing import Any

from config_core import get_frontend_schema, read_masked_config, save_config_with_merge
from fastapi import APIRouter, HTTPException, Request

from .backends.google_drive import GoogleDriveBackend
from .config import StorageConfig, _DEFAULT_CONFIG_PATH

logger = logging.getLogger(__name__)

control_router = APIRouter(prefix="/control", tags=["control"])


class StorageManager:
    """Manages the storage backend lifecycle and configuration.

    Follows the same manager pattern as BotManager/AgentManager — mutable
    state attached to ``app.state``, frozen config resolved on demand.
    """

    def __init__(self) -> None:
        self._config: StorageConfig | None = None
        self._backend: GoogleDriveBackend | None = None
        self._last_error: str | None = None

    @property
    def config(self) -> StorageConfig | None:
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
            self._config = StorageConfig.resolve()
        except ValueError as e:
            self._last_error = str(e)
            logger.error("Configuration missing: %s", e)
            return

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

    def _is_configured(self) -> bool:
        """Check whether the minimum required config fields are present."""
        try:
            config = StorageConfig.resolve()
            return bool(config.drive_client_id and config.drive_client_secret)
        except Exception:
            logger.exception("Failed to resolve storage config during status check")
            return False

    def status(self) -> dict[str, Any]:
        """Return the current storage manager status."""
        return {
            "configured": self._is_configured(),
            "running": self.running,
            "last_error": self._last_error,
        }


# --------------------------------------------------------------------------
# /control/* routes
# --------------------------------------------------------------------------


def _get_manager(request: Request) -> StorageManager:
    return request.app.state.manager


@control_router.get("/status")
async def get_status(request: Request) -> dict[str, Any]:
    """Return storage manager status."""
    return _get_manager(request).status()


@control_router.post("/start")
async def start_manager(request: Request) -> dict[str, Any]:
    """Start the storage manager."""
    manager = _get_manager(request)
    try:
        await manager.start()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


@control_router.post("/stop")
async def stop_manager(request: Request) -> dict[str, Any]:
    """Stop the storage manager."""
    manager = _get_manager(request)
    await manager.stop()
    return manager.status()


@control_router.post("/restart")
async def restart_manager(request: Request) -> dict[str, Any]:
    """Restart the storage manager with fresh config."""
    manager = _get_manager(request)
    try:
        await manager.restart()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


@control_router.get("/schema")
async def get_schema() -> dict[str, Any]:
    """Return the file storage config field schema."""
    return get_frontend_schema(
        StorageConfig,
        title="File Storage Configuration",
        description=(
            "Configures the storage backend used for uploading build artifacts."
            " The current implementation uses Google Drive — enter your OAuth"
            " credentials below, then connect via the dashboard."
        )
    )


@control_router.get("/config")
async def get_config() -> dict[str, Any]:
    """Return current config values with secrets masked."""
    return read_masked_config(StorageConfig, _DEFAULT_CONFIG_PATH)


@control_router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    payload = await request.json()
    save_config_with_merge(StorageConfig, _DEFAULT_CONFIG_PATH, payload)
    return {"status": "saved"}
