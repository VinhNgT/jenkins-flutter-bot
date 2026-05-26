"""Service control API routes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, File, UploadFile
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ..dependencies import ManagerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["services"])

_MANAGED_SERVICES = {"bot", "agent", "file_manager", "builds"}


@router.get("/status")
async def get_service_status(manager: ManagerDep) -> dict[str, Any]:
    """Return the current status of all controllable services."""
    return {
        "bot": await manager.services.status("bot"),
        "agent": await manager.services.status("agent"),
        "file_manager": await manager.services.status("file_manager"),
        "builds": await manager.services.status("builds"),
    }


@router.get("/stream", response_class=EventSourceResponse)
async def stream_services_status(
    request: Request,
    manager: ManagerDep,
):
    """Stream service statuses using Server-Sent Events (SSE)."""
    last_sent_hash = None

    try:
        while True:
            if await request.is_disconnected():
                logger.info("Service status SSE client disconnected")
                break

            status = {
                "bot": await manager.services.status("bot"),
                "agent": await manager.services.status("agent"),
                "file_manager": await manager.services.status("file_manager"),
                "builds": await manager.services.status("builds"),
            }

            # Canonical JSON serialization for hashing/deduplication
            current_str = json.dumps(status, sort_keys=True)
            current_hash = hashlib.md5(current_str.encode()).hexdigest()

            if last_sent_hash is None or current_hash != last_sent_hash:
                last_sent_hash = current_hash
                yield ServerSentEvent(data=status, event="status")

            await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info("Service status SSE streaming cancelled")
        raise


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
