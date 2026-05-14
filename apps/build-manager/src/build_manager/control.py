"""BuildManager and /control/* API routes.

The manager owns the BuildCoordinator lifecycle and resolves configuration.
Control routes expose status, lifecycle, schema, and config CRUD — the
standard interface that config-hub proxies to.
"""

from __future__ import annotations

import logging
from typing import Any

from config_core import get_frontend_schema, read_masked_config, save_config_with_merge
from fastapi import APIRouter, HTTPException, Request

from .builds.coordinator import BuildCoordinator
from .config import BuildConfig, _DEFAULT_CONFIG_PATH

logger = logging.getLogger(__name__)

control_router = APIRouter(prefix="/control", tags=["control"])


class BuildManager:
    """Manages the build coordinator lifecycle and configuration.

    Attached to ``app.state.manager`` during lifespan.
    """

    def __init__(self) -> None:
        self._coordinator: BuildCoordinator | None = None
        self._last_error: str | None = None

    @property
    def coordinator(self) -> BuildCoordinator:
        """Return the active coordinator — initialised lazily."""
        if self._coordinator is None:
            raise RuntimeError("Build coordinator not initialised")
        return self._coordinator

    async def start(self) -> None:
        """Initialise the coordinator from the current config."""
        try:
            config = BuildConfig.resolve()
        except ValueError as e:
            self._last_error = str(e)
            logger.error("Configuration missing: %s", e)
            return

        coord = BuildCoordinator(
            data_dir=config.build_data_path,
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
        self._last_error = None
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
        await self.start()

    @property
    def running(self) -> bool:
        return self._coordinator is not None

    def _is_configured(self) -> bool:
        """Check whether the minimum required config fields are present."""
        try:
            config = BuildConfig.resolve()
            return bool(config.jenkins_url and config.jenkins_user)
        except Exception:
            logger.exception("Failed to resolve build config during status check")
            return False

    def status(self) -> dict[str, Any]:
        """Return the current build manager status."""
        return {
            "configured": self._is_configured(),
            "running": self.running,
            "last_error": self._last_error,
        }


# ---------------------------------------------------------------------------
# Control routes
# ---------------------------------------------------------------------------


def _get_manager(request: Request) -> BuildManager:
    return request.app.state.manager


@control_router.get("/status")
async def get_status(request: Request) -> dict[str, Any]:
    """Return build manager status."""
    return _get_manager(request).status()


@control_router.post("/start")
async def start_manager(request: Request) -> dict[str, Any]:
    """Start the build manager."""
    manager = _get_manager(request)
    try:
        await manager.start()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


@control_router.post("/stop")
async def stop_manager(request: Request) -> dict[str, Any]:
    """Stop the build manager."""
    manager = _get_manager(request)
    await manager.stop()
    return manager.status()


@control_router.post("/restart")
async def restart_manager(request: Request) -> dict[str, Any]:
    """Restart the build manager with fresh config."""
    manager = _get_manager(request)
    try:
        await manager.restart()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


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
async def get_config() -> dict[str, Any]:
    """Return current config values with secrets masked."""
    return read_masked_config(BuildConfig, _DEFAULT_CONFIG_PATH)


@control_router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    payload = await request.json()
    save_config_with_merge(BuildConfig, _DEFAULT_CONFIG_PATH, payload)
    return {"status": "saved"}
