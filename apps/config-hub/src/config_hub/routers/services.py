"""Service control API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..dependencies import ManagerDep

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
