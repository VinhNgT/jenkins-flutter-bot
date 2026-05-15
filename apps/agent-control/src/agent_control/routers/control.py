"""Control routes — /control/*."""

from __future__ import annotations

from typing import Any

from config_core import get_frontend_schema, read_masked_config, save_config_with_merge
from fastapi import APIRouter, Request

from ..config import AgentConfig, _DEFAULT_CONFIG_PATH
from ..dependencies import ManagerDep

router = APIRouter(prefix="/control", tags=["control"])


@router.post("/start")
async def start_agent(manager: ManagerDep) -> dict[str, Any]:
    """Start the Jenkins agent if it is not already running."""
    await manager.start()
    return manager.status()


@router.post("/stop")
async def stop_agent(manager: ManagerDep) -> dict[str, Any]:
    """Stop the Jenkins agent if it is running."""
    await manager.stop()
    return manager.status()


@router.post("/restart")
async def restart_agent(manager: ManagerDep) -> dict[str, Any]:
    """Restart the Jenkins agent using the current resolved config."""
    await manager.restart()
    return manager.status()


@router.get("/status")
async def agent_status(manager: ManagerDep) -> dict[str, Any]:
    """Report whether the Jenkins agent is configured and running."""
    return manager.status()


@router.get("/schema")
async def get_schema() -> dict[str, Any]:
    """Return the agent module's config field schema."""
    return get_frontend_schema(
        AgentConfig,
        title="Jenkins Agent Configuration",
        description=(
            "Configures the Flutter build agent that connects to Jenkins as an"
            " inbound node. The agent runs inside Docker with Flutter and Android"
            " SDKs pre-installed. Obtain the agent secret from the node's status"
            " page in Jenkins after creating the node."
        )
    )


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """Return current config values with secrets masked."""
    return read_masked_config(AgentConfig, _DEFAULT_CONFIG_PATH)


@router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    payload = await request.json()
    save_config_with_merge(AgentConfig, _DEFAULT_CONFIG_PATH, payload)
    return {"status": "saved"}
