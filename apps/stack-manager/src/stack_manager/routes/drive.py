"""Google Drive OAuth API routes."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..config_store import load_json
from ..manager import StackManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drive", tags=["drive"])


def _drive_credentials(
    drive_data: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Extract Drive client credentials from drive config."""
    from config_schema import nested_get

    client_id = nested_get(drive_data, "drive.client_id")
    client_secret = nested_get(drive_data, "drive.client_secret")
    return (
        str(client_id) if client_id not in (None, "") else None,
        str(client_secret) if client_secret not in (None, "") else None,
    )


def _drive_callback_url(request: Request) -> str:
    """Build the OAuth callback URL from the current request context."""
    return str(request.url_for("drive_oauth_callback"))


@router.get("/status")
async def get_drive_status(request: Request) -> dict[str, Any]:
    """Return current Google Drive connection status."""
    manager: StackManager = request.app.state.manager
    drive_data = load_json(manager.paths.drive)
    client_id, client_secret = _drive_credentials(drive_data)

    if not client_id or not client_secret:
        return {
            "configured": False,
            "connected": False,
            "token_path": str(manager.drive_oauth.token_path),
        }

    status = manager.drive_oauth.status(client_id, client_secret)
    status["configured"] = True
    return status


@router.post("/connect/start")
async def start_drive_connect(request: Request) -> dict[str, Any]:
    """Start the Drive OAuth flow — returns the authorization URL."""
    manager: StackManager = request.app.state.manager
    drive_data = load_json(manager.paths.drive)
    client_id, client_secret = _drive_credentials(drive_data)

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail=(
                "Configure the Drive client ID and client secret "
                "in the Google Drive tab first."
            ),
        )

    return {
        "auth_url": manager.drive_oauth.start(
            client_id,
            client_secret,
            _drive_callback_url(request),
        )
    }


@router.post("/connect/exchange")
async def exchange_drive_code(request: Request) -> dict[str, Any]:
    """Exchange a manually-pasted auth code for tokens (headless flow).

    Used by tg-admin-bot via the stack-manager API instead of managing
    DriveOAuth directly.
    """
    manager: StackManager = request.app.state.manager
    body = await request.json()
    code = body.get("code", "")
    client_id = body.get("client_id", "")
    client_secret = body.get("client_secret", "")

    if not code or not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="code, client_id, and client_secret are required.",
        )

    try:
        manager.drive_oauth.exchange_code(code, client_id, client_secret)
        return {"success": True}
    except Exception as exc:
        logger.exception("Drive code exchange failed")
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/oauth/callback", name="drive_oauth_callback")
async def drive_oauth_callback(request: Request) -> Any:
    """Handle the Google OAuth redirect callback."""
    from fastapi.templating import Jinja2Templates

    manager: StackManager = request.app.state.manager
    templates: Jinja2Templates = request.app.state.templates
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

    try:
        manager.drive_oauth.exchange_callback(str(request.url))
    except RuntimeError as exc:
        return templates.TemplateResponse(
            request=request,
            name="oauth_callback.html",
            context={
                "title": "Google Drive Connection Failed",
                "message": str(exc),
                "payload_json": json.dumps(
                    {
                        "type": "drive-oauth-complete",
                        "success": False,
                        "message": str(exc),
                    }
                ),
            },
            status_code=400,
        )
    except Exception as exc:
        msg = f"Drive authorization failed: {exc}"
        logger.exception("Drive OAuth callback failed")
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
async def disconnect_drive(request: Request) -> dict[str, Any]:
    """Delete the saved OAuth token, disconnecting the current Google account."""
    manager: StackManager = request.app.state.manager
    deleted = manager.drive_oauth.delete_tokens()
    if not deleted:
        return {"disconnected": False, "detail": "No token file found."}
    return {"disconnected": True}
