"""OAuth authentication routes — /api/auth/*.

These routes are only functional when the Google Drive backend is
active. In ephemeral mode, the status endpoint reports the backend
type and all OAuth-specific routes return 404.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..dependencies import ManagerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
async def auth_status(manager: ManagerDep) -> dict[str, Any]:
    """Return current auth/connection status.

    For ephemeral backends, reports as always connected.
    For Drive backends, returns OAuth connection state.
    """
    if manager.backend is None:
        return {"backend": manager.backend_type, "connected": False, "configured": False}
    return await manager.backend.status()


@router.post("/connect/start")
async def connect_start(manager: ManagerDep, request: Request) -> dict[str, str]:
    """Start the OAuth flow. Expects ``{redirect_uri: "..."}``.

    Returns ``{auth_url: "..."}``.
    Only available with the Google Drive backend.
    """
    drive = manager.google_drive_backend
    if drive is None:
        raise HTTPException(
            status_code=404,
            detail="OAuth is not available with the current storage backend",
        )

    body = await request.json()
    redirect_uri = body.get("redirect_uri", "")
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri required")

    auth_url = drive.start_auth(redirect_uri=redirect_uri)
    return {"auth_url": auth_url}


@router.post("/connect/exchange")
async def connect_exchange(manager: ManagerDep, request: Request) -> dict[str, str]:
    """Exchange a manually-pasted auth code for tokens.

    Expects ``{code: "..."}``.  Used by the admin bot (headless flow).
    Only available with the Google Drive backend.
    """
    drive = manager.google_drive_backend
    if drive is None:
        raise HTTPException(
            status_code=404,
            detail="OAuth is not available with the current storage backend",
        )

    body = await request.json()
    code = body.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="code required")

    try:
        await drive.exchange_code(code=code)
        return {"status": "connected"}
    except Exception:
        logger.exception("OAuth code exchange failed")
        raise HTTPException(status_code=400, detail="Code exchange failed")


@router.get("/callback")
async def oauth_callback(manager: ManagerDep, request: Request) -> dict[str, str]:
    """Handle the browser OAuth redirect callback.

    Google redirects here with ``?code=...``. The full URL is passed
    to ``exchange_callback()``.
    Only available with the Google Drive backend.
    """
    drive = manager.google_drive_backend
    if drive is None:
        raise HTTPException(
            status_code=404,
            detail="OAuth is not available with the current storage backend",
        )

    try:
        await drive.exchange_callback(str(request.url))
        return {"status": "connected"}
    except Exception:
        logger.exception("OAuth callback exchange failed")
        raise HTTPException(status_code=400, detail="Callback exchange failed")


@router.post("/callback")
async def oauth_callback_proxy(manager: ManagerDep, request: Request) -> dict[str, str]:
    """Exchange a proxied authorization response URL for tokens.

    Used by config-hub: Google redirects there, which forwards the full
    ``authorization_response`` URL here.
    Only available with the Google Drive backend.
    """
    drive = manager.google_drive_backend
    if drive is None:
        raise HTTPException(
            status_code=404,
            detail="OAuth is not available with the current storage backend",
        )

    body = await request.json()
    authorization_response = body.get("authorization_response", "")
    if not authorization_response:
        raise HTTPException(status_code=400, detail="authorization_response required")

    try:
        await drive.exchange_callback(authorization_response)
        return {"status": "connected"}
    except Exception:
        logger.exception("Proxied OAuth callback exchange failed")
        raise HTTPException(status_code=400, detail="Callback exchange failed")


@router.delete("/disconnect")
@router.delete("/token")
async def disconnect(manager: ManagerDep) -> dict[str, Any]:
    """Delete saved OAuth tokens.

    Only functional with the Google Drive backend.
    """
    drive = manager.google_drive_backend
    if drive is None:
        return {"disconnected": False, "detail": "Not using Google Drive backend"}
    deleted = drive.delete_tokens()
    return {"disconnected": deleted}
