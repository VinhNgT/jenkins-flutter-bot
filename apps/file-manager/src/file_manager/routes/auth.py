"""OAuth authentication routes — /api/auth/*."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..control import StorageManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _mgr(request: Request) -> StorageManager:
    return request.app.state.manager


def _require_backend(mgr: StorageManager) -> None:
    if mgr.backend is None or mgr.config is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")


@router.get("/status")
async def auth_status(request: Request) -> dict[str, Any]:
    """Return current OAuth connection status."""
    mgr = _mgr(request)
    if mgr.backend is None or mgr.config is None:
        return {"connected": False, "detail": "not initialised"}
    return mgr.backend.status(
        client_id=mgr.config.drive_client_id,
        client_secret=mgr.config.drive_client_secret,
    )


@router.post("/connect/start")
async def connect_start(request: Request) -> dict[str, str]:
    """Start the OAuth flow. Expects ``{redirect_uri: "..."}``.

    Returns ``{auth_url: "..."}``.
    """
    mgr = _mgr(request)
    _require_backend(mgr)
    assert mgr.backend is not None
    assert mgr.config is not None

    body = await request.json()
    redirect_uri = body.get("redirect_uri", "")
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri required")

    auth_url = mgr.backend.start_auth(
        client_id=mgr.config.drive_client_id,
        client_secret=mgr.config.drive_client_secret,
        redirect_uri=redirect_uri,
    )
    return {"auth_url": auth_url}


@router.post("/connect/exchange")
async def connect_exchange(request: Request) -> dict[str, str]:
    """Exchange a manually-pasted auth code for tokens.

    Expects ``{code: "..."}``.  Used by the admin bot (headless flow).
    """
    mgr = _mgr(request)
    _require_backend(mgr)
    assert mgr.backend is not None
    assert mgr.config is not None

    body = await request.json()
    code = body.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="code required")

    try:
        mgr.backend.exchange_code(
            code=code,
            client_id=mgr.config.drive_client_id,
            client_secret=mgr.config.drive_client_secret,
        )
        return {"status": "connected"}
    except Exception:
        logger.exception("OAuth code exchange failed")
        raise HTTPException(status_code=400, detail="Code exchange failed")


@router.get("/callback")
async def oauth_callback(request: Request) -> dict[str, str]:
    """Handle the browser OAuth redirect callback.

    Google redirects here with ``?code=...``. The full URL is passed
    to ``exchange_callback()``.
    """
    mgr = _mgr(request)
    _require_backend(mgr)
    assert mgr.backend is not None

    try:
        mgr.backend.exchange_callback(str(request.url))
        return {"status": "connected"}
    except Exception:
        logger.exception("OAuth callback exchange failed")
        raise HTTPException(status_code=400, detail="Callback exchange failed")


@router.post("/callback")
async def oauth_callback_proxy(request: Request) -> dict[str, str]:
    """Exchange a proxied authorization response URL for tokens.

    Used by stack-manager: Google redirects to SM, SM forwards the full
    ``authorization_response`` URL here.
    """
    mgr = _mgr(request)
    _require_backend(mgr)
    assert mgr.backend is not None

    body = await request.json()
    authorization_response = body.get("authorization_response", "")
    if not authorization_response:
        raise HTTPException(
            status_code=400, detail="authorization_response required"
        )

    try:
        mgr.backend.exchange_callback(authorization_response)
        return {"status": "connected"}
    except Exception:
        logger.exception("Proxied OAuth callback exchange failed")
        raise HTTPException(status_code=400, detail="Callback exchange failed")


@router.delete("/disconnect")
@router.delete("/token")
async def disconnect(request: Request) -> dict[str, Any]:
    """Delete saved OAuth tokens."""
    mgr = _mgr(request)
    if mgr.backend is None:
        return {"disconnected": False}
    deleted = mgr.backend.delete_tokens()
    return {"disconnected": deleted}
