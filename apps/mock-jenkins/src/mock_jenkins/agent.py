"""Mock agent-control server — emulates the flutter-agent's control API.

Serves the same /control/* endpoints that config-hub queries, using the
real AgentSettings schema to stay in sync automatically.  Unlike the real
agent-control (which manages a Jenkins subprocess), this mock simply
tracks configured/running state so the dashboard lifecycle is testable.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from pathlib import Path
import uvicorn
from agent_control.config import AgentSettings, _DEFAULT_CONFIG_PATH
from config_core import format_validation_error, get_frontend_schema, read_masked_config, save_config_with_merge, setup_service_logging
from config_core.schema import resolve_config_path
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from pydantic import ValidationError
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
        self._started_at: float | None = None
        self._vpn_connected: bool = False
        # Use resolve_config_path so this redirects to tmp_path in test
        # environments, matching the real VpnManager's path resolution.
        self.OVPN_PATH = resolve_config_path(Path("/app/data/client.ovpn"))

    @property
    def running(self) -> bool:
        return self._running

    def status(self) -> dict[str, Any]:
        """Return the current agent status."""
        config_error: str | None = None
        config: AgentSettings | None = None
        try:
            config = AgentSettings.load()
        except Exception as exc:
            config_error = format_validation_error(exc)
        
        uploaded = self.OVPN_PATH.exists()
        size = self.OVPN_PATH.stat().st_size if uploaded else 0
        
        result: dict[str, Any] = {
            "configured": config_error is None,
            "running": self._running,
            "last_error": self._last_error,
            "config_error": config_error,
            "vpn": {
                "uploaded": uploaded,
                "size": size,
                "connected": self._vpn_connected,
            }
        }
        if config is not None:
            result["agent_name"] = config.agent_name
        if self._started_at is not None:
            result["started_at"] = self._started_at
        return result

    async def start(self) -> None:
        """Simulate starting the agent — validates config first."""
        if self._running:
            return

        try:
            AgentSettings.load()
        except (ValueError, ValidationError) as e:
            self._last_error = str(e)
            raise StartupError(str(e)) from e

        self._running = True
        self._last_error = None
        self._started_at = time.time()
        logger.info("Mock agent started (simulated)")

    async def stop(self) -> None:
        """Simulate stopping the agent."""
        self._running = False
        self._started_at = None
        self._vpn_connected = False
        logger.info("Mock agent stopped (simulated)")

    async def restart(self) -> None:
        """Simulate restarting the agent."""
        await self.stop()
        await self.start()



# ---------------------------------------------------------------------------
# FastAPI agent control mock
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage mock agent lifecycle on startup/shutdown."""
    try:
        await app.state.manager.start()
    except StartupError:
        logger.warning(
            "Mock agent not auto-started: %s",
            app.state.manager.status()["last_error"],
        )
    yield


def create_app() -> FastAPI:
    """Application factory for the mock agent-control server."""
    app = FastAPI(title="mock-agent-control", lifespan=lifespan)
    app.state.manager = MockAgentState()

    @app.exception_handler(StartupError)
    async def handle_startup_error(
        request: Request, exc: StartupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/control/status")
    async def agent_status(request: Request) -> dict[str, Any]:
        """Report the current agent status."""
        logger.info("GET /control/status")
        return request.app.state.manager.status()

    @app.get("/control/schema")
    async def agent_schema() -> dict[str, Any]:
        """Return the agent config schema (from real AgentSettings)."""
        logger.info("GET /control/schema")
        return get_frontend_schema(
            AgentSettings,
            title="Jenkins Agent Configuration",
            description=(
                "Configures the Flutter build agent that connects to Jenkins as an"
                " inbound node. The agent runs inside Docker with Flutter and Android"
                " SDKs pre-installed. Obtain the agent secret from the node's status"
                " page in Jenkins after creating the node."
            ),
        )

    @app.post("/control/start")
    async def agent_start(request: Request) -> dict[str, Any]:
        """Start the mock agent — validates config first."""
        logger.info("POST /control/start")
        await request.app.state.manager.start()
        return request.app.state.manager.status()

    @app.post("/control/stop")
    async def agent_stop(request: Request) -> dict[str, Any]:
        """Stop the mock agent."""
        logger.info("POST /control/stop")
        await request.app.state.manager.stop()
        return request.app.state.manager.status()

    @app.post("/control/restart")
    async def agent_restart(request: Request) -> dict[str, Any]:
        """Restart the mock agent — re-validates config."""
        logger.info("POST /control/restart")
        await request.app.state.manager.restart()
        return request.app.state.manager.status()

    @app.get("/control/config")
    async def agent_get_config() -> dict[str, Any]:
        """Return current config values with secrets masked."""
        logger.info("GET /control/config")
        return read_masked_config(AgentSettings, _DEFAULT_CONFIG_PATH)

    @app.put("/control/config")
    async def agent_put_config(request: Request) -> dict[str, Any]:
        """Save config values with deep merge."""
        logger.info("PUT /control/config")
        payload = await request.json()
        save_config_with_merge(AgentSettings, _DEFAULT_CONFIG_PATH, payload)
        return {"status": "saved"}

    @app.post("/control/vpn/upload")
    async def mock_upload_vpn(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
        """Mock VPN file upload."""
        logger.info("POST /control/vpn/upload")
        manager = request.app.state.manager
        manager.OVPN_PATH.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        try:
            manager.OVPN_PATH.write_bytes(content)
        except OSError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"status": "uploaded", "size": len(content)}

    @app.get("/control/vpn/status")
    async def mock_vpn_status(request: Request) -> dict[str, Any]:
        """Mock VPN status."""
        logger.info("GET /control/vpn/status")
        return request.app.state.manager.status()["vpn"]

    @app.delete("/control/vpn/upload")
    async def mock_delete_vpn(request: Request) -> dict[str, Any]:
        """Mock VPN file deletion."""
        logger.info("DELETE /control/vpn/upload")
        manager = request.app.state.manager
        if manager.OVPN_PATH.exists():
            try:
                manager.OVPN_PATH.unlink()
            except OSError as e:
                raise HTTPException(status_code=500, detail=str(e))
        return {"status": "deleted"}

    @app.post("/control/vpn/connect")
    async def mock_connect_vpn(request: Request) -> dict[str, Any]:
        """Mock VPN connection."""
        logger.info("POST /control/vpn/connect")
        manager = request.app.state.manager
        
        # Check settings
        config = AgentSettings.load()
        if not config.vpn_enabled:
            logger.warning("VPN not enabled in mock settings.")
            return {"status": "disabled", "vpn": manager.status()["vpn"]}
            
        if not manager.OVPN_PATH.exists():
            raise HTTPException(status_code=400, detail="VPN is enabled but no .ovpn file has been uploaded.")
            
        manager._vpn_connected = True
        return {"status": "connecting", "vpn": manager.status()["vpn"]}

    @app.post("/control/vpn/disconnect")
    async def mock_disconnect_vpn(request: Request) -> dict[str, Any]:
        """Mock VPN disconnection."""
        logger.info("POST /control/vpn/disconnect")
        manager = request.app.state.manager
        manager._vpn_connected = False
        return {"status": "disconnected", "vpn": manager.status()["vpn"]}

    return app



def cli() -> None:
    """CLI entry point for the mock agent server."""
    setup_service_logging()
    logger.info("Starting mock-agent-control on port %d", MOCK_AGENT_PORT)
    uvicorn.run(create_app(), host="0.0.0.0", port=MOCK_AGENT_PORT)

