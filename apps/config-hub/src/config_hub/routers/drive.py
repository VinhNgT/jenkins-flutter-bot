"""Google Drive OAuth API routes — proxies to file-manager service."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from ..dependencies import ManagerDep, TemplatesDep

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
    """Start the Drive OAuth flow via file-manager — returns the auth URL."""
    # Build the redirect URI from the current request context so the
    # OAuth callback comes back to *this* service (config-hub), which
    # then proxies the exchange to file-manager.
    callback_url = str(request.url_for("drive_oauth_callback"))

    try:
        resp = await manager.fm_client.post(
            f"{manager.file_manager_url}/api/auth/connect/start",
            json={"redirect_uri": callback_url},
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
    """Exchange a manually-pasted auth code for tokens (headless flow)."""
    body = await request.json()

    try:
        resp = await manager.fm_client.post(
            f"{manager.file_manager_url}/api/auth/connect/exchange",
            json=body,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.exception("file-manager rejected code exchange")
        detail = exc.response.text if exc.response else str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except Exception as exc:
        logger.exception("Cannot reach file-manager for code exchange")
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/oauth/callback", name="drive_oauth_callback")
async def drive_oauth_callback(
    manager: ManagerDep, templates: TemplatesDep, request: Request
) -> Any:
    """Handle the Google OAuth redirect callback.

    Receives the OAuth redirect from Google, then proxies the full
    callback URL to file-manager for token exchange.
    """
    error = request.query_params.get("error")

    if error:
        description = request.query_params.get("error_description")
        message = "Google authorization was not completed."
        if description:
            message = f"{message} {description}"
        return templates.TemplateResponse(
            request=request,
            name="oauth_callback.html",
            context={
                "title": "Google Drive Connection Failed",
                "message": message,
                "payload_json": json.dumps(
                    {
                        "type": "drive-oauth-complete",
                        "success": False,
                        "message": message,
                    }
                ),
            },
            status_code=400,
        )

    # Forward the full callback URL to file-manager for token exchange
    try:
        resp = await manager.fm_client.post(
            f"{manager.file_manager_url}/api/auth/callback",
            json={"authorization_response": str(request.url)},
        )
        resp.raise_for_status()
    except Exception as exc:
        msg = f"Drive authorization failed: {exc}"
        logger.exception("Drive OAuth callback proxy failed")
        return templates.TemplateResponse(
            request=request,
            name="oauth_callback.html",
            context={
                "title": "Google Drive Connection Failed",
                "message": msg,
                "payload_json": json.dumps(
                    {
                        "type": "drive-oauth-complete",
                        "success": False,
                        "message": msg,
                    }
                ),
            },
            status_code=400,
        )

    message = "Google Drive is connected. You can return to the dashboard."
    return templates.TemplateResponse(
        request=request,
        name="oauth_callback.html",
        context={
            "title": "Google Drive Connected",
            "message": message,
            "payload_json": json.dumps(
                {
                    "type": "drive-oauth-complete",
                    "success": True,
                    "message": message,
                }
            ),
        },
    )


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
