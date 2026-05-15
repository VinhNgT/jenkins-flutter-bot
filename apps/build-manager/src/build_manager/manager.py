"""Build manager lifecycle and configuration.

The manager owns the BuildCoordinator lifecycle and resolves configuration.
Attached to ``app.state.manager`` during lifespan.
"""

from __future__ import annotations

import logging
from typing import Any

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
        )

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
        """Check whether required config fields are present."""
        try:
            BuildSettings.load()
            return True
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        """Return the current build manager status."""
        return {
            "configured": self._is_configured(),
            "running": self.running,
            "last_error": self._last_error,
        }
