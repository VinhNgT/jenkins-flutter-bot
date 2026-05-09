"""Export routes — generate production .env files and download OAuth tokens."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from stack_manager import DriveOAuth, ServiceClient, generate_env, load_json
from ..settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/env")
async def export_env(request: Request) -> dict[str, Any]:
    """Generate a production .env file from the current saved configuration."""
    settings: Settings = request.app.state.settings
    client: ServiceClient = request.app.state.service_client
    drive_oauth: DriveOAuth = request.app.state.drive_oauth

    # Fetch schemas (which include env_var)
    bot_schema = await client.schema("bot")
    agent_schema = await client.schema("agent")

    # Read raw config data (including secrets)
    bot_data = load_json(settings.bot_config_path)
    agent_data = load_json(settings.agent_config_path)

    env_content, warnings = generate_env(
        bot_config=bot_data,
        agent_config=agent_data,
        bot_schema=bot_schema,
        agent_schema=agent_schema,
        oauth_exists=drive_oauth.token_path.exists(),
    )
    return {"env_content": env_content, "warnings": warnings}


@router.get("/oauth", response_model=None)
async def export_oauth(request: Request) -> FileResponse | JSONResponse:
    """Download the oauth.json token file."""
    drive_oauth: DriveOAuth = request.app.state.drive_oauth
    token_path: Path = drive_oauth.token_path

    if not token_path.exists():
        return JSONResponse(
            status_code=404,
            content={
                "detail": (
                    "OAuth token not found. Complete the Google Drive"
                    " setup in the Dashboard tab first."
                ),
            },
        )

    return FileResponse(
        path=str(token_path),
        filename="oauth.json",
        media_type="application/json",
    )
