"""Build manager lifecycle and configuration.

The manager owns the BuildCoordinator lifecycle and resolves configuration.
Attached to ``app.state.manager`` during lifespan.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from config_core import format_validation_error
from pydantic import ValidationError

from .builds.coordinator import BuildCoordinator
from .config import BuildSettings

logger = logging.getLogger(__name__)


class StartupError(Exception):
    """Raised when the build manager fails to start."""


class BuildManager:
    """Manages the build coordinator lifecycle and configuration."""

    def __init__(self) -> None:
        self._coordinator: BuildCoordinator | None = None
        self._last_error: str | None = None
        self._started_at: float | None = None

    @property
    def coordinator(self) -> BuildCoordinator:
        """Return the active coordinator — initialised lazily."""
        if self._coordinator is None:
            raise RuntimeError("Build coordinator not initialised")
        return self._coordinator

    async def start(self) -> None:
        """Initialise the coordinator from the current config."""
        try:
            config = BuildSettings.load()
        except (ValueError, ValidationError) as e:
            self._last_error = str(e)
            raise StartupError(str(e)) from e

        coord = BuildCoordinator(
            data_dir=config.build_data_path,
            self_url=config.self_url,
            file_manager_url=config.file_manager_url,
            max_recent_builds=config.max_recent_builds,
            build_timeout=config.build_timeout,
        )

        coord.init_jenkins(
            url=config.jenkins_url,
            user=config.jenkins_user,
            api_token=config.jenkins_api_token,
            job_name=config.jenkins_job_name,
        )

        self._coordinator = coord
        self._last_error = None
        self._started_at = time.time()
        logger.info("Build manager started")

    async def stop(self) -> None:
        """Shut down the coordinator and its HTTP clients."""
        if self._coordinator is not None:
            await self._coordinator.close()
            self._coordinator = None
            self._started_at = None
            logger.info("Build manager stopped")

    async def restart(self) -> None:
        """Stop and re-start with fresh config."""
        await self.stop()
        await self.start()

    @property
    def running(self) -> bool:
        return self._coordinator is not None

    def status(self) -> dict[str, Any]:
        """Return the current build manager status."""
        config_error: str | None = None
        try:
            BuildSettings.load()
        except Exception as exc:
            config_error = format_validation_error(exc)
        result: dict[str, Any] = {
            "configured": config_error is None,
            "running": self.running,
            "last_error": self._last_error,
            "config_error": config_error,
        }
        if self._coordinator is not None:
            result["pending_builds"] = self._coordinator.tracker.pending_count
        if self._started_at is not None:
            result["started_at"] = self._started_at
        return result
