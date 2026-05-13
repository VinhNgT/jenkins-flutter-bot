"""Storage manager and /control/* routes for file-manager."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from config_schema import deep_merge
from fastapi import APIRouter, Request

from .backends.google_drive import GoogleDriveBackend
from .config import StorageConfig, _DEFAULT_CONFIG_PATH
from .schema import get_registry

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

    @property
    def config(self) -> StorageConfig | None:
        return self._config

    @property
    def backend(self) -> GoogleDriveBackend | None:
        return self._backend

    def _config_path(self) -> Path:
        val = os.environ.get("CONFIG_PATH")
        return Path(val) if val else _DEFAULT_CONFIG_PATH

    def _token_path(self) -> Path:
        return self._config_path().parent / "oauth.json"

    def start(self) -> None:
        """Resolve config and initialise the storage backend."""
        config_path = self._config_path()
        try:
            self._config = StorageConfig.resolve(config_path)
        except ValueError as e:
            logger.error("Configuration missing: %s", e)
            return

        self._backend = GoogleDriveBackend(self._token_path())
        logger.info("StorageManager started")

    def reload_config(self) -> None:
        """Re-resolve configuration from disk."""
        config_path = self._config_path()
        self._config = StorageConfig.resolve(config_path)
        logger.info("StorageManager config reloaded")


# --------------------------------------------------------------------------
# /control/* routes
# --------------------------------------------------------------------------


def _manager(request: Request) -> StorageManager:
    return request.app.state.manager


@control_router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    mgr = _manager(request)
    running = mgr.backend is not None
    result: dict[str, Any] = {"running": running}
    if running and mgr.config:
        result["storage"] = mgr.backend.status(  # type: ignore[union-attr]
            client_id=mgr.config.drive_client_id,
            client_secret=mgr.config.drive_client_secret,
        )
    return result


@control_router.get("/schema")
async def schema() -> dict[str, Any]:
    return get_registry().serialize()


@control_router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    """Return current config values with secrets masked."""
    mgr = _manager(request)
    config_path = mgr._config_path()
    if not config_path.exists():
        return {"values": {}, "secret_lengths": {}}

    data = json.loads(config_path.read_text())

    # Mask secrets
    secret_lengths: dict[str, int] = {}
    for key in get_registry().secret_keys:
        parts = key.split(".")
        current: Any = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
                break
        if current and isinstance(current, str):
            secret_lengths[key] = len(current)
            # Remove the secret from the response
            container = data
            for part in parts[:-1]:
                container = container.get(part, {})
            if isinstance(container, dict):
                container.pop(parts[-1], None)

    return {"values": data, "secret_lengths": secret_lengths}


@control_router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    mgr = _manager(request)
    config_path = mgr._config_path()

    payload = await request.json()

    # Strip empty/None secrets to avoid overwriting existing values
    for key in get_registry().secret_keys:
        parts = key.split(".")
        container: Any = payload
        for part in parts[:-1]:
            if isinstance(container, dict):
                container = container.get(part, {})
            else:
                container = None
                break
        if isinstance(container, dict) and not container.get(parts[-1]):
            container.pop(parts[-1], None)

    # Deep merge with existing
    existing: dict[str, Any] = {}
    if config_path.exists():
        existing = json.loads(config_path.read_text())

    merged = deep_merge(existing, payload)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(merged, indent=2))

    mgr.reload_config()
    return {"status": "saved"}


@control_router.post("/start")
async def start(request: Request) -> dict[str, Any]:
    mgr = _manager(request)
    mgr.start()
    return {"status": "started"}


@control_router.post("/stop")
async def stop(request: Request) -> dict[str, Any]:
    # Storage manager doesn't have a heavy stop procedure
    return {"status": "stopped"}


@control_router.post("/restart")
async def restart(request: Request) -> dict[str, Any]:
    mgr = _manager(request)
    mgr.start()
    return {"status": "restarted"}
