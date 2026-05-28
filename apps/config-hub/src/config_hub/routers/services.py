"""Service control API routes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, File, UploadFile

from ..dependencies import ManagerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["services"])

_MANAGED_SERVICES = {"bot", "agent", "file_manager", "builds"}


@router.get("/status")
async def get_service_status(manager: ManagerDep) -> dict[str, Any]:
    """Return the current status of all controllable services concurrently."""
    scopes = ["bot", "agent", "file_manager", "builds"]
    results = await asyncio.gather(*(manager.services.status(s) for s in scopes))
    return dict(zip(scopes, results))



@router.post("/{service}/{action}")
async def control_service(
    manager: ManagerDep, service: str, action: str
) -> dict[str, Any]:
    """Start, stop, or restart a service."""
    if service not in _MANAGED_SERVICES:
        raise HTTPException(status_code=404, detail="Unknown service")
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(status_code=404, detail="Unknown action")

    method = getattr(manager.services, action)
    return await method(service)


@router.post("/agent/vpn/upload")
async def proxy_vpn_upload(manager: ManagerDep, file: UploadFile = File(...)) -> dict[str, Any]:
    """Proxy multipart .ovpn configuration file upload to agent-control."""
    content = await file.read()
    return await manager.services.upload_vpn_file(content, file.filename or "client.ovpn")



@router.get("/agent/vpn/status")
async def proxy_vpn_status(manager: ManagerDep) -> dict[str, Any]:
    """Proxy VPN status request to agent-control."""
    return await manager.services.vpn_status()


@router.delete("/agent/vpn/upload")
async def proxy_vpn_delete(manager: ManagerDep) -> dict[str, Any]:
    """Proxy VPN config deletion to agent-control."""
    return await manager.services.delete_vpn_file()


@router.post("/agent/vpn/connect")
async def proxy_vpn_connect(manager: ManagerDep) -> dict[str, Any]:
    """Proxy VPN connect request to agent-control."""
    return await manager.services.vpn_connect()


@router.post("/agent/vpn/disconnect")
async def proxy_vpn_disconnect(manager: ManagerDep) -> dict[str, Any]:
    """Proxy VPN disconnect request to agent-control."""
    return await manager.services.vpn_disconnect()
