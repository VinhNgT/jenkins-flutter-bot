"""Mock agent-control server — emulates the flutter-agent's control API.

Serves the same /control/* endpoints that config-hub queries, using the
real AgentConfig schema to stay in sync automatically.  Unlike the real
agent-control (which manages a Jenkins subprocess), this mock simply
tracks configured/running state so the dashboard lifecycle is testable.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import uvicorn
from agent_control.config import AgentConfig, _DEFAULT_CONFIG_PATH
from config_core import get_frontend_schema, read_masked_config, save_config_with_merge
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

MOCK_AGENT_PORT = int(os.environ.get("MOCK_AGENT_PORT", "9091"))


# ---------------------------------------------------------------------------
# Mock agent state — mirrors real AgentManager's lifecycle
# ---------------------------------------------------------------------------


class StartupError(Exception):
    """Raised when the mock agent fails to start."""


class MockAgentState:
    """Tracks configured/running state for the mock agent.

    Mirrors the real ``AgentManager`` interface used by control routes:
    ``status()``, ``start()``, ``stop()``, ``restart()``.
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._last_error: str | None = None

    def _is_configured(self) -> bool:
        """Check whether the required config fields are present."""
        try:
            config = AgentConfig.resolve()
            return bool(config.secret)
        except Exception:
            return False

    @property
    def running(self) -> bool:
        return self._running

    def status(self) -> dict[str, Any]:
        """Return the current agent status."""
        return {
            "configured": self._is_configured(),
            "running": self._running,
            "last_error": self._last_error,
        }

    async def start(self) -> None:
        """Simulate starting the agent — validates config first."""
        if self._running:
            return

        try:
            config = AgentConfig.resolve()
        except ValueError as e:
            self._last_error = str(e)
            raise StartupError(str(e)) from e

        if not config.secret:
            msg = "Missing required configuration: JENKINS_SECRET"
            self._last_error = msg
            raise StartupError(msg)

        self._running = True
        self._last_error = None
        logger.info("Mock agent started (simulated)")

    async def stop(self) -> None:
        """Simulate stopping the agent."""
        self._running = False
        logger.info("Mock agent stopped (simulated)")

    async def restart(self) -> None:
        """Simulate restarting the agent."""
        await self.stop()
        await self.start()


# ---------------------------------------------------------------------------
# FastAPI agent control mock
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Application factory for the mock agent-control server."""
    # Ensure AgentConfig.resolve() can find the same JSON file that
    # save_config_with_merge writes to (via _DEFAULT_CONFIG_PATH).
    os.environ.setdefault("CONFIG_PATH", str(_DEFAULT_CONFIG_PATH))

    app = FastAPI(title="mock-agent-control")
    state = MockAgentState()

    @app.exception_handler(StartupError)
    async def handle_startup_error(
        request: Request, exc: StartupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/control/status")
    async def agent_status() -> dict[str, Any]:
        """Report the current agent status."""
        logger.info("GET /control/status")
        return state.status()

    @app.get("/control/schema")
    async def agent_schema() -> dict[str, Any]:
        """Return the agent config schema (from real AgentConfig)."""
        logger.info("GET /control/schema")
        return get_frontend_schema(
            AgentConfig,
            title="Jenkins Agent Configuration",
            description=(
                "Configures the Flutter build agent that connects to Jenkins as an"
                " inbound node. The agent runs inside Docker with Flutter and Android"
                " SDKs pre-installed. Obtain the agent secret from the node's status"
                " page in Jenkins after creating the node."
            ),
        )

    @app.post("/control/start")
    async def agent_start() -> dict[str, Any]:
        """Start the mock agent — validates config first."""
        logger.info("POST /control/start")
        await state.start()
        return state.status()

    @app.post("/control/stop")
    async def agent_stop() -> dict[str, Any]:
        """Stop the mock agent."""
        logger.info("POST /control/stop")
        await state.stop()
        return state.status()

    @app.post("/control/restart")
    async def agent_restart() -> dict[str, Any]:
        """Restart the mock agent — re-validates config."""
        logger.info("POST /control/restart")
        await state.restart()
        return state.status()

    @app.get("/control/config")
    async def agent_get_config() -> dict[str, Any]:
        """Return current config values with secrets masked."""
        logger.info("GET /control/config")
        return read_masked_config(AgentConfig, _DEFAULT_CONFIG_PATH)

    @app.put("/control/config")
    async def agent_put_config(request: Request) -> dict[str, Any]:
        """Save config values with deep merge."""
        logger.info("PUT /control/config")
        payload = await request.json()
        save_config_with_merge(AgentConfig, _DEFAULT_CONFIG_PATH, payload)
        return {"status": "saved"}

    return app


def cli() -> None:
    """CLI entry point for the mock agent server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    logger.info("Starting mock-agent-control on port %d", MOCK_AGENT_PORT)
    uvicorn.run(create_app(), host="0.0.0.0", port=MOCK_AGENT_PORT)
