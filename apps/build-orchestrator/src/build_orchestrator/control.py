"""OrchestratorManager and /control/* API routes.

The manager owns the JenkinsClient lifecycle and resolves configuration.
Control routes expose status, lifecycle, schema, and config CRUD — the
standard interface that config-hub proxies to.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from config_schema import deep_merge, nested_get, nested_set
from fastapi import APIRouter, Request

from .builds.orchestrator import BuildOrchestrator
from .config import OrchestratorConfig
from .schema import (
    MODULE_DESCRIPTION,
    MODULE_TITLE,
    ORCHESTRATOR_FIELDS,
    ORCHESTRATOR_INFRA,
    ORCHESTRATOR_SECRET_FIELDS,
    serialize_schema,
)
from .settings import Settings

logger = logging.getLogger(__name__)

control_router = APIRouter(prefix="/control", tags=["control"])


class OrchestratorManager:
    """Manages the build orchestrator lifecycle and configuration.

    Attached to ``app.state.manager`` during lifespan.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._orchestrator: BuildOrchestrator | None = None

    @property
    def orchestrator(self) -> BuildOrchestrator:
        """Return the active orchestrator — initialised lazily."""
        if self._orchestrator is None:
            raise RuntimeError("Orchestrator not initialised")
        return self._orchestrator

    def start(self) -> None:
        """Initialise the orchestrator from the current config."""
        config = OrchestratorConfig.resolve(self.settings.config_path)

        orch = BuildOrchestrator(
            data_dir=self.settings.build_data_path,
            self_url=config.self_url,
            file_manager_url=config.file_manager_url,
        )

        # Initialise Jenkins client if credentials are available
        if config.jenkins_url and config.jenkins_user and config.jenkins_api_token:
            orch.init_jenkins(
                url=config.jenkins_url,
                user=config.jenkins_user,
                api_token=config.jenkins_api_token,
                job_name=config.jenkins_job_name,
            )

        self._orchestrator = orch
        logger.info("Orchestrator started")

    async def stop(self) -> None:
        """Shut down the orchestrator and its HTTP clients."""
        if self._orchestrator is not None:
            await self._orchestrator.close()
            self._orchestrator = None
            logger.info("Orchestrator stopped")

    async def restart(self) -> None:
        """Stop and re-start with fresh config."""
        await self.stop()
        self.start()

    @property
    def running(self) -> bool:
        return self._orchestrator is not None


# ---------------------------------------------------------------------------
# Control routes
# ---------------------------------------------------------------------------


@control_router.get("/status")
async def get_status(request: Request) -> dict[str, Any]:
    """Return orchestrator status."""
    manager: OrchestratorManager = request.app.state.manager
    result: dict[str, Any] = {"running": manager.running}
    if manager.running:
        result["builds"] = manager.orchestrator.tracker.to_dict()
    return result


@control_router.post("/start")
async def start(request: Request) -> dict[str, Any]:
    """Start the orchestrator."""
    manager: OrchestratorManager = request.app.state.manager
    if manager.running:
        return {"status": "already_running"}
    try:
        manager.start()
        return {"status": "started"}
    except Exception:
        logger.exception("Failed to start orchestrator")
        return {"status": "error", "detail": "Start failed — check logs"}


@control_router.post("/stop")
async def stop(request: Request) -> dict[str, Any]:
    """Stop the orchestrator."""
    manager: OrchestratorManager = request.app.state.manager
    await manager.stop()
    return {"status": "stopped"}


@control_router.post("/restart")
async def restart(request: Request) -> dict[str, Any]:
    """Restart the orchestrator with fresh config."""
    manager: OrchestratorManager = request.app.state.manager
    try:
        await manager.restart()
        return {"status": "restarted"}
    except Exception:
        logger.exception("Failed to restart orchestrator")
        return {"status": "error", "detail": "Restart failed — check logs"}


@control_router.get("/schema")
async def get_schema() -> dict[str, Any]:
    """Return the orchestrator's config field schema."""
    schema = serialize_schema(ORCHESTRATOR_FIELDS, MODULE_TITLE, MODULE_DESCRIPTION)
    schema["infra"] = serialize_schema(
        ORCHESTRATOR_INFRA, MODULE_TITLE, MODULE_DESCRIPTION
    )["fields"]
    return schema


@control_router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    """Return current config values with secrets masked."""
    manager: OrchestratorManager = request.app.state.manager
    config_path = manager.settings.config_path

    data: dict[str, Any] = {}
    if config_path and config_path.exists():
        data = json.loads(config_path.read_text())

    secret_lengths: dict[str, int | bool] = {}
    for key in ORCHESTRATOR_SECRET_FIELDS:
        value = nested_get(data, key)
        if value not in (None, ""):
            secret_lengths[key] = len(str(value))
            nested_set(data, key, None)
        else:
            secret_lengths[key] = False

    return {"values": data, "secret_lengths": secret_lengths}


@control_router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    manager: OrchestratorManager = request.app.state.manager
    config_path = manager.settings.config_path

    if not config_path:
        return {"status": "error", "detail": "CONFIG_PATH not set"}

    payload = await request.json()

    # Strip empty/None secrets to avoid overwriting existing values
    for key in ORCHESTRATOR_SECRET_FIELDS:
        value = nested_get(payload, key)
        if value is None or value == "":
            parts = key.split(".")
            container: Any = payload
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

    merged = deep_merge(existing, payload)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(merged, indent=2))

    return {"status": "saved"}
