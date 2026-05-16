"""OAuth authentication routes — /api/auth/*."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..dependencies import ManagerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
async def auth_status(manager: ManagerDep) -> dict[str, Any]:
    """Return current OAuth connection status."""
    if manager.backend is None or manager.config is None:
        return {"connected": False, "detail": "not initialised"}
    return await manager.backend.status(
        client_id=manager.config.drive_client_id,
        client_secret=manager.config.drive_client_secret,
    )


@router.post("/connect/start")
async def connect_start(manager: ManagerDep, request: Request) -> dict[str, str]:
    """Start the OAuth flow. Expects ``{redirect_uri: "..."}``.

    Returns ``{auth_url: "..."}``.
    """
    if manager.backend is None or manager.config is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    body = await request.json()
    redirect_uri = body.get("redirect_uri", "")
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri required")

    auth_url = manager.backend.start_auth(
        client_id=manager.config.drive_client_id,
        client_secret=manager.config.drive_client_secret,
        redirect_uri=redirect_uri,
    )
    return {"auth_url": auth_url}


@router.post("/connect/exchange")
async def connect_exchange(manager: ManagerDep, request: Request) -> dict[str, str]:
    """Exchange a manually-pasted auth code for tokens.

    Expects ``{code: "..."}``.  Used by the admin bot (headless flow).
    """
    if manager.backend is None or manager.config is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    body = await request.json()
    code = body.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="code required")

    try:
        await manager.backend.exchange_code(
            code=code,
            client_id=manager.config.drive_client_id,
            client_secret=manager.config.drive_client_secret,
        )
        return {"status": "connected"}
    except Exception:
        logger.exception("OAuth code exchange failed")
        raise HTTPException(status_code=400, detail="Code exchange failed")


@router.get("/callback")
async def oauth_callback(manager: ManagerDep, request: Request) -> dict[str, str]:
    """Handle the browser OAuth redirect callback.

    Google redirects here with ``?code=...``. The full URL is passed
    to ``exchange_callback()``.
    """
    if manager.backend is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    try:
        await manager.backend.exchange_callback(str(request.url))
        return {"status": "connected"}
    except Exception:
        logger.exception("OAuth callback exchange failed")
        raise HTTPException(status_code=400, detail="Callback exchange failed")


@router.post("/callback")
async def oauth_callback_proxy(manager: ManagerDep, request: Request) -> dict[str, str]:
    """Exchange a proxied authorization response URL for tokens.

    Used by config-hub: Google redirects here, which forwards the full
    ``authorization_response`` URL here.
    """
    if manager.backend is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    body = await request.json()
    authorization_response = body.get("authorization_response", "")
    if not authorization_response:
        raise HTTPException(status_code=400, detail="authorization_response required")

    try:
        await manager.backend.exchange_callback(authorization_response)
        return {"status": "connected"}
    except Exception:
        logger.exception("Proxied OAuth callback exchange failed")
        raise HTTPException(status_code=400, detail="Callback exchange failed")


@router.delete("/disconnect")
@router.delete("/token")
async def disconnect(manager: ManagerDep) -> dict[str, Any]:
    """Delete saved OAuth tokens."""
    if manager.backend is None:
        return {"disconnected": False}
    deleted = manager.backend.delete_tokens()
    return {"disconnected": deleted}
