"""Control routes — /control/*."""

from __future__ import annotations

from typing import Any

from config_core import (
    get_buffer_logs,
    get_frontend_schema,
    read_masked_config,
    save_config_with_merge,
)
from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ..config import AgentSettings, _DEFAULT_CONFIG_PATH
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
        AgentSettings,
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
    return read_masked_config(AgentSettings, _DEFAULT_CONFIG_PATH)


@router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    payload = await request.json()
    save_config_with_merge(AgentSettings, _DEFAULT_CONFIG_PATH, payload)
    return {"status": "saved"}


# Maximum VPN config file size: 1 MB (.ovpn files are text-based and tiny).
MAX_VPN_FILE_SIZE = 1 * 1024 * 1024


@router.post("/vpn/upload")
async def upload_vpn_file(manager: ManagerDep, file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload client.ovpn config file (write-only)."""
    manager.vpn.OVPN_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()

    if len(content) > MAX_VPN_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"VPN config too large (max {MAX_VPN_FILE_SIZE // (1024 * 1024)} MB)",
        )

    try:
        manager.vpn.OVPN_PATH.write_bytes(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write file: {e}")
    return {"status": "uploaded", "size": len(content)}


@router.get("/vpn/status")
async def get_vpn_status(manager: ManagerDep) -> dict[str, Any]:
    """Return VPN file and connection status."""
    return manager.vpn.status()


@router.delete("/vpn/upload")
async def delete_vpn_file(manager: ManagerDep) -> dict[str, Any]:
    """Delete client.ovpn config file."""
    if manager.vpn.OVPN_PATH.exists():
        try:
            manager.vpn.OVPN_PATH.unlink()
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")
    return {"status": "deleted"}


@router.post("/vpn/connect")
async def connect_vpn(manager: ManagerDep) -> dict[str, Any]:
    """Connect OpenVPN tunnel."""
    try:
        await manager.vpn_connect()
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "connecting", "vpn": manager.vpn.status()}


@router.post("/vpn/disconnect")
async def disconnect_vpn(manager: ManagerDep) -> dict[str, Any]:
    """Disconnect OpenVPN tunnel."""
    try:
        await manager.vpn_disconnect()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "disconnected", "vpn": manager.vpn.status()}


@router.get("/logs")
async def get_logs() -> dict[str, Any]:
    """Return recent log lines from the in-memory ring buffer."""
    return {"lines": get_buffer_logs()}
