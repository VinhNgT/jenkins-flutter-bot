"""Agent lifecycle management and HTTP control routes."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .config import AgentConfig

logger = logging.getLogger(__name__)


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

        logger.info("Starting Jenkins agent: %s", command)
        try:
            self._process = subprocess.Popen(command, text=True)
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

    def status(self) -> dict[str, Any]:
        """Return the current agent manager status."""
        return {
            "configured": self._config is not None,
            "running": self.running,
            "pid": self._process.pid if self.running and self._process else None,
            "last_error": self._last_error,
            "agent_name": self._config.agent_name if self._config else None,
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
