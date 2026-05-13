"""BuildManager and /control/* API routes.

The manager owns the BuildCoordinator lifecycle and resolves configuration.
Control routes expose status, lifecycle, schema, and config CRUD — the
standard interface that config-hub proxies to.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from config_core import ConfigDocument, get_frontend_schema
from fastapi import APIRouter, Request

from .builds.coordinator import BuildCoordinator
from .config import BuildConfig
from .settings import Settings

logger = logging.getLogger(__name__)

control_router = APIRouter(prefix="/control", tags=["control"])


class BuildManager:
    """Manages the build coordinator lifecycle and configuration.

    Attached to ``app.state.manager`` during lifespan.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._coordinator: BuildCoordinator | None = None

    @property
    def coordinator(self) -> BuildCoordinator:
        """Return the active coordinator — initialised lazily."""
        if self._coordinator is None:
            raise RuntimeError("Build coordinator not initialised")
        return self._coordinator

    def start(self) -> None:
        """Initialise the coordinator from the current config."""
        try:
            config = BuildConfig.resolve(self.settings.config_path)
        except ValueError as e:
            logger.error("Configuration missing: %s", e)
            return

        coord = BuildCoordinator(
            data_dir=self.settings.build_data_path,
            self_url=config.self_url,
            file_manager_url=config.file_manager_url,
        )

        # Initialise Jenkins client if credentials are available
        if config.jenkins_url and config.jenkins_user and config.jenkins_api_token:
            coord.init_jenkins(
                url=config.jenkins_url,
                user=config.jenkins_user,
                api_token=config.jenkins_api_token,
                job_name=config.jenkins_job_name,
            )

        self._coordinator = coord
        logger.info("Build manager started")

    async def stop(self) -> None:
        """Shut down the coordinator and its HTTP clients."""
        if self._coordinator is not None:
            await self._coordinator.close()
            self._coordinator = None
            logger.info("Build manager stopped")

    async def restart(self) -> None:
        """Stop and re-start with fresh config."""
        await self.stop()
        self.start()

    @property
    def running(self) -> bool:
        return self._coordinator is not None


# ---------------------------------------------------------------------------
# Control routes
# ---------------------------------------------------------------------------


@control_router.get("/status")
async def get_status(request: Request) -> dict[str, Any]:
    """Return build manager status."""
    manager: BuildManager = request.app.state.manager
    result: dict[str, Any] = {"running": manager.running}
    if manager.running:
        result["builds"] = manager.coordinator.tracker.to_dict()
    return result


@control_router.post("/start")
async def start(request: Request) -> dict[str, Any]:
    """Start the build manager."""
    manager: BuildManager = request.app.state.manager
    if manager.running:
        return {"status": "already_running"}
    try:
        manager.start()
        return {"status": "started"}
    except Exception:
        logger.exception("Failed to start build manager")
        return {"status": "error", "detail": "Start failed — check logs"}


@control_router.post("/stop")
async def stop(request: Request) -> dict[str, Any]:
    """Stop the build manager."""
    manager: BuildManager = request.app.state.manager
    await manager.stop()
    return {"status": "stopped"}


@control_router.post("/restart")
async def restart(request: Request) -> dict[str, Any]:
    """Restart the build manager with fresh config."""
    manager: BuildManager = request.app.state.manager
    try:
        await manager.restart()
        return {"status": "restarted"}
    except Exception:
        logger.exception("Failed to restart build manager")
        return {"status": "error", "detail": "Restart failed — check logs"}


def _get_secret_keys() -> list[str]:
    keys = []
    for name, field in BuildConfig.model_fields.items():
        extra = field.json_schema_extra or {}
        if extra.get("secret"):
            keys.append(extra.get("json_key", name))
    return keys


@control_router.get("/schema")
async def get_schema() -> dict[str, Any]:
    """Return the build manager's config field schema."""
    return get_frontend_schema(
        BuildConfig,
        title="Build Manager Configuration",
        description=(
            "Configures the build manager's connection to Jenkins and the"
            " Git repository used for builds."
        )
    )


@control_router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    """Return current config values with secrets masked."""
    manager: BuildManager = request.app.state.manager
    config_path = manager.settings.config_path

    data: dict[str, Any] = {}
    if config_path and config_path.exists():
        data = json.loads(config_path.read_text())

    doc = ConfigDocument(data)
    secret_lengths: dict[str, int | bool] = {}
    for key in _get_secret_keys():
        value = doc.get(key)
        if value not in (None, ""):
            secret_lengths[key] = len(str(value))
            doc.set(key, None)
        else:
            secret_lengths[key] = False

    return {"values": doc.data, "secret_lengths": secret_lengths}


@control_router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    manager: BuildManager = request.app.state.manager
    config_path = manager.settings.config_path

    payload = await request.json()
    payload_doc = ConfigDocument(payload)

    # Strip empty/None secrets to avoid overwriting existing values
    for key in _get_secret_keys():
        value = payload_doc.get(key)
        if value is None or value == "":
            parts = key.split(".")
            container: Any = payload_doc.data
            for part in parts[:-1]:
                if isinstance(container, dict):
                    container = container.get(part, {})
                else:
                    container = None
                    break
            if isinstance(container, dict):
                container.pop(parts[-1], None)

    # Deep merge with existing
    existing: dict[str, Any] = {}
    if config_path.exists():
        existing = json.loads(config_path.read_text())

    doc = ConfigDocument(existing)
    doc.merge(payload_doc.data)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(doc.data, indent=2))

    return {"status": "saved"}
