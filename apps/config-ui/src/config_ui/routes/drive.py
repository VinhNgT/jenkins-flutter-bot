"""Google Drive OAuth API routes."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..config_store import load_json, nested_get
from ..settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drive", tags=["drive"])


def _drive_credentials(
    ui_config: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Extract Drive client credentials from UI config."""
    client_id = nested_get(ui_config, "drive.client_id")
    client_secret = nested_get(ui_config, "drive.client_secret")
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
    settings: Settings = request.app.state.settings
    drive_oauth = request.app.state.drive_oauth
    ui = load_json(settings.ui_config_path)
    client_id, client_secret = _drive_credentials(ui)

    if not client_id or not client_secret:
        return {
            "configured": False,
            "connected": False,
            "token_path": str(drive_oauth.token_path),
        }

    status = drive_oauth.status(client_id, client_secret)
    status["configured"] = True
    return status


@router.post("/connect/start")
async def start_drive_connect(request: Request) -> dict[str, Any]:
    """Start the Drive OAuth flow — returns the authorization URL."""
    settings: Settings = request.app.state.settings
    drive_oauth = request.app.state.drive_oauth
    ui = load_json(settings.ui_config_path)
    client_id, client_secret = _drive_credentials(ui)

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail=(
                "Configure the Drive client ID and client secret "
                "in the Google Drive tab first."
            ),
        )

    return {
        "auth_url": drive_oauth.start(
            client_id,
            client_secret,
            _drive_callback_url(request),
        )
    }


@router.get("/oauth/callback", name="drive_oauth_callback")
async def drive_oauth_callback(request: Request) -> Any:
    """Handle the Google OAuth redirect callback."""
    from fastapi.templating import Jinja2Templates

    drive_oauth = request.app.state.drive_oauth
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
        drive_oauth.exchange_callback(str(request.url))
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
    drive_oauth = request.app.state.drive_oauth
    token_path = drive_oauth.token_path
    if not token_path.exists():
        return {"disconnected": False, "detail": "No token file found."}
    try:
        token_path.unlink()
        logger.info("Removed Drive OAuth token at %s", token_path)
        return {"disconnected": True}
    except Exception:
        logger.exception("Failed to remove Drive OAuth token at %s", token_path)
        raise HTTPException(status_code=500, detail="Failed to remove token file.")

