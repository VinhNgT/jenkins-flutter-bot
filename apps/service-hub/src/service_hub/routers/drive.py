"""Google Drive OAuth API routes — proxies to file-manager service."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from ..dependencies import ManagerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drive", tags=["drive"])


@router.get("/status")
async def get_drive_status(manager: ManagerDep) -> dict[str, Any]:
    """Return current Google Drive connection status from file-manager."""
    try:
        resp = await manager.fm_client.get(
            f"{manager.file_manager_url}/api/auth/status"
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("Failed to reach file-manager for drive status")
        return {"configured": False, "connected": False, "available": False}


@router.post("/connect/start")
async def start_drive_connect(manager: ManagerDep, request: Request) -> dict[str, Any]:
    """Start the Drive OAuth flow via file-manager."""
    body = await request.json()
    redirect_uri = body.get("redirect_uri")
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="Missing redirect_uri")

    try:
        resp = await manager.fm_client.post(
            f"{manager.file_manager_url}/api/auth/connect/start",
            json={"redirect_uri": redirect_uri},
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.exception("file-manager rejected OAuth start")
        detail = exc.response.text if exc.response else str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except Exception as exc:
        logger.exception("Cannot reach file-manager for OAuth start")
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/connect/exchange")
async def exchange_drive_code(manager: ManagerDep, request: Request) -> dict[str, Any]:
    """Exchange OAuth code/response for tokens via file-manager."""
    body = await request.json()

    try:
        # If payload contains authorization_response, proxy to /api/auth/callback
        if "authorization_response" in body:
            target_url = f"{manager.file_manager_url}/api/auth/callback"
        else:
            target_url = f"{manager.file_manager_url}/api/auth/connect/exchange"

        resp = await manager.fm_client.post(target_url, json=body)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.exception("file-manager rejected code exchange")
        detail = exc.response.text if exc.response else str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except Exception as exc:
        logger.exception("Cannot reach file-manager for code exchange")
        raise HTTPException(status_code=502, detail=str(exc))


@router.delete("/token")
async def disconnect_drive(manager: ManagerDep) -> dict[str, Any]:
    """Disconnect Drive by deleting OAuth tokens via file-manager."""
    try:
        resp = await manager.fm_client.delete(
            f"{manager.file_manager_url}/api/auth/token"
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("Failed to disconnect Drive via file-manager")
        return {"disconnected": False, "detail": "Cannot reach file-manager."}
