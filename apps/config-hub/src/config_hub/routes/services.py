"""Service control API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..manager import ConfigHubManager

router = APIRouter(prefix="/api/services", tags=["services"])

_MANAGED_SERVICES = {"bot", "agent", "file_manager", "orchestrator"}


@router.get("/status")
async def get_service_status(request: Request) -> dict[str, Any]:
    """Return the current status of all controllable services."""
    manager: ConfigHubManager = request.app.state.manager
    return {
        "bot": await manager.services.status("bot"),
        "agent": await manager.services.status("agent"),
        "file_manager": await manager.services.status("file_manager"),
        "orchestrator": await manager.services.status("orchestrator"),
    }


@router.post("/{service}/{action}")
async def control_service(
    request: Request, service: str, action: str
) -> dict[str, Any]:
    """Start, stop, or restart a service."""
    if service not in _MANAGED_SERVICES:
        raise HTTPException(status_code=404, detail="Unknown service")
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(status_code=404, detail="Unknown action")

    manager: ConfigHubManager = request.app.state.manager
    method = getattr(manager.services, action)
    return await method(service)
