"""Agent lifecycle management.

Manages the Jenkins inbound agent subprocess — spawning, stopping, and
reporting status.  Attached to ``app.state.manager`` during lifespan.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from .config import AgentConfig

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


class AgentManager:
    """Manage the Jenkins inbound agent subprocess."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._last_error: str | None = None
        self._config: AgentConfig | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    async def start(self) -> None:
        """Spawn the Jenkins inbound agent as a child process."""
        if self.running:
            return

        try:
            config = AgentConfig.resolve()
        except ValueError as e:
            self._last_error = str(e)
            logger.error("Configuration missing: %s", e)
            return

        if not config.secret:
            raise ValueError("Missing required configuration: JENKINS_SECRET")

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
            logger.exception("Failed to start Jenkins agent")
            raise

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

    def _is_configured(self) -> bool:
        """Check whether the required config fields are present."""
        try:
            config = AgentConfig.resolve()
            return bool(config.secret)
        except Exception:
            logger.exception("Failed to resolve agent config during status check")
            return False

    def status(self) -> dict[str, Any]:
        """Return the current agent manager status."""
        return {
            "configured": self._is_configured(),
            "running": self.running,
            "last_error": self._last_error,
        }
