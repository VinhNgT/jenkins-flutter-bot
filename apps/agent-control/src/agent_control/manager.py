"""Agent lifecycle management.

Manages the Jenkins inbound agent subprocess — spawning, stopping, and
reporting status.  Attached to ``app.state.manager`` during lifespan.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from config_core import format_validation_error
from pydantic import ValidationError

from .config import AgentSettings

logger = logging.getLogger(__name__)

# The jenkins-agent entrypoint script reads these env vars and converts them
# to CLI flags automatically. Since AgentManager passes all values as explicit
# CLI arguments, we must strip these from the subprocess environment to avoid
# duplicate flags (e.g. two -url values, which breaks WebSocket mode).
_JENKINS_AGENT_ENV_VARS = {
    "JENKINS_URL",
    "JENKINS_SECRET",
    "JENKINS_AGENT_NAME",
    "JENKINS_TUNNEL",
    "JENKINS_WEB_SOCKET",
    "JENKINS_NAME",
}


class StartupError(Exception):
    """Raised when the agent manager fails to start."""


class AgentManager:
    """Manage the Jenkins inbound agent subprocess."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._last_error: str | None = None
        self._config: AgentSettings | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    async def start(self) -> None:
        """Spawn the Jenkins inbound agent as a child process."""
        if self.running:
            return

        try:
            config = AgentSettings.load()
        except (ValueError, ValidationError) as e:
            self._last_error = str(e)
            raise StartupError(str(e)) from e

        command = [
            "/usr/local/bin/jenkins-agent",
            "-url",
            config.jenkins_url,
            "-secret",
            config.secret,
            "-name",
            config.agent_name,
        ]
        if config.web_socket:
            command.append("-webSocket")
        if config.tunnel:
            command.extend(["-tunnel", config.tunnel])

        # Build a clean env so the jenkins-agent script doesn't duplicate our
        # explicit CLI flags from its own env-var handling.
        clean_env = {
            k: v for k, v in os.environ.items() if k not in _JENKINS_AGENT_ENV_VARS
        }

        logger.info("Starting Jenkins agent: %s", command)
        try:
            self._process = subprocess.Popen(command, text=True, env=clean_env)
            self._config = config
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            raise StartupError(str(exc)) from exc

    async def stop(self) -> None:
        """Send SIGTERM, wait 5s, then SIGKILL if needed."""
        if not self._process:
            return

        logger.info("Stopping Jenkins agent...")
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        finally:
            self._process = None
            self._config = None

    async def restart(self) -> None:
        """Restart the Jenkins agent."""
        await self.stop()
        await self.start()

    def status(self) -> dict[str, Any]:
        """Return the current agent manager status."""
        config_error: str | None = None
        try:
            AgentSettings.load()
        except Exception as exc:
            config_error = format_validation_error(exc)
        return {
            "configured": config_error is None,
            "running": self.running,
            "last_error": self._last_error,
            "config_error": config_error,
        }
