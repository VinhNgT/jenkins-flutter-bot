"""Service control API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from stack_manager import ServiceClient

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("/status")
async def get_service_status(request: Request) -> dict[str, Any]:
    """Return the current status of all controllable services."""
    client: ServiceClient = request.app.state.service_client
    return {
        "bot": await client.status("bot"),
        "agent": await client.status("agent"),
    }


@router.post("/{service}/{action}")
async def control_service(
    request: Request, service: str, action: str
) -> dict[str, Any]:
    """Start, stop, or restart a service."""
    if service not in {"bot", "agent"}:
        raise HTTPException(status_code=404, detail="Unknown service")
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(status_code=404, detail="Unknown action")

    client: ServiceClient = request.app.state.service_client
    if action == "start":
        return await client.start(service)
    if action == "stop":
        return await client.stop(service)
    return await client.restart(service)
