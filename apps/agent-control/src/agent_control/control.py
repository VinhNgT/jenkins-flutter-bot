"""Agent lifecycle management and HTTP control routes."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException, Request

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

    def start(self, config: AgentConfig) -> None:
        """Spawn the Jenkins inbound agent as a child process."""
        if self.running:
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

    def stop(self) -> None:
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
        active_config = self._config if self.running else None
        return {
            "configured": self._is_configured(),
            "running": self.running,
            "pid": self._process.pid if self.running and self._process else None,
            "last_error": self._last_error,
            "agent_name": active_config.agent_name if active_config else None,
        }


control_router = APIRouter(prefix="/control", tags=["control"])


def _get_manager(request: Request) -> AgentManager:
    return request.app.state.manager


@control_router.post("/start")
async def start_agent(request: Request) -> dict[str, Any]:
    """Start the Jenkins agent if it is not already running."""
    manager = _get_manager(request)
    config = AgentConfig.resolve()
    try:
        manager.start(config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


@control_router.post("/stop")
async def stop_agent(request: Request) -> dict[str, Any]:
    """Stop the Jenkins agent if it is running."""
    manager = _get_manager(request)
    manager.stop()
    return manager.status()


@control_router.post("/restart")
async def restart_agent(request: Request) -> dict[str, Any]:
    """Restart the Jenkins agent using the current resolved config."""
    manager = _get_manager(request)
    config = AgentConfig.resolve()
    try:
        manager.stop()
        manager.start(config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


@control_router.get("/status")
async def agent_status(request: Request) -> dict[str, Any]:
    """Report whether the Jenkins agent is configured and running."""
    return _get_manager(request).status()


@control_router.get("/schema")
async def get_schema() -> dict[str, Any]:
    """Return the agent module's config field schema."""
    from .schema import (
        AGENT_FIELDS,
        AGENT_INFRA,
        MODULE_DESCRIPTION,
        MODULE_TITLE,
        serialize_schema,
    )

    schema = serialize_schema(AGENT_FIELDS, MODULE_TITLE, MODULE_DESCRIPTION)
    schema["infra"] = serialize_schema(
        AGENT_INFRA, MODULE_TITLE, MODULE_DESCRIPTION
    )["fields"]
    return schema
