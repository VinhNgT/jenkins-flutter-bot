"""Config transfer routes — export/import configuration as tarballs."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import Response
from stack_manager import (
    DriveOAuth,
    ServiceClient,
    build_export_tarball,
    generate_compose_vars,
    generate_env_files,
    import_tarball,
    load_json,
)

from ..schema import (
    DRIVE_FIELDS,
    DRIVE_INFRA,
    MODULE_DESCRIPTION,
    MODULE_TITLE,
    serialize_schema,
)
from ..settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["config-transfer"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _gather_export_data(
    request: Request,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, dict[str, Any], DriveOAuth]:
    """Fetch schemas and config data needed for export."""
    settings: Settings = request.app.state.settings
    client: ServiceClient = request.app.state.service_client
    drive_oauth: DriveOAuth = request.app.state.drive_oauth

    bot_schema = await client.schema("bot")
    agent_schema = await client.schema("agent")
    drive_schema = serialize_schema(DRIVE_FIELDS, MODULE_TITLE, MODULE_DESCRIPTION)
    drive_schema["infra"] = serialize_schema(
        DRIVE_INFRA, MODULE_TITLE, MODULE_DESCRIPTION
    )["fields"]
    bot_data = load_json(settings.bot_config_path)
    agent_data = load_json(settings.agent_config_path)
    drive_data = load_json(settings.drive_config_path)

    return bot_data, agent_data, drive_data, bot_schema, agent_schema, drive_schema, drive_oauth


# ---------------------------------------------------------------------------
# Export routes
# ---------------------------------------------------------------------------


@router.get("/export/env")
async def export_env(request: Request) -> dict[str, Any]:
    """Generate per-service env file contents for preview."""
    bot_data, agent_data, drive_data, bot_schema, agent_schema, drive_schema, _ = (
        await _gather_export_data(request)
    )

    files, warnings = generate_env_files(
        bot_config=bot_data,
        agent_config=agent_data,
        bot_schema=bot_schema,
        agent_schema=agent_schema,
        drive_config=drive_data,
        drive_schema=drive_schema,
    )
    compose_vars = {
        "bot": generate_compose_vars(bot_data, bot_schema, "Telegram Bot"),
        "agent": generate_compose_vars(agent_data, agent_schema, "Jenkins Agent"),
    }
    return {"files": files, "compose_vars": compose_vars, "warnings": warnings}


@router.get("/export/tarball", response_model=None)
async def export_tarball(request: Request) -> Response:
    """Download a .tar.gz containing all config files."""
    bot_data, agent_data, drive_data, bot_schema, agent_schema, drive_schema, drive_oauth = (
        await _gather_export_data(request)
    )

    files, _ = generate_env_files(
        bot_config=bot_data,
        agent_config=agent_data,
        bot_schema=bot_schema,
        agent_schema=agent_schema,
        drive_config=drive_data,
        drive_schema=drive_schema,
    )
    tarball = build_export_tarball(files, oauth_token_path=drive_oauth.token_path)

    return Response(
        content=tarball,
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=jfb-config.tar.gz"},
    )


# ---------------------------------------------------------------------------
# Import routes
# ---------------------------------------------------------------------------


@router.post("/import/tarball")
async def import_config_tarball(
    request: Request,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Import configuration from a .tar.gz export."""
    settings: Settings = request.app.state.settings
    client: ServiceClient = request.app.state.service_client
    drive_oauth: DriveOAuth = request.app.state.drive_oauth

    bot_schema = await client.schema("bot")
    agent_schema = await client.schema("agent")
    drive_schema = serialize_schema(DRIVE_FIELDS, MODULE_TITLE, MODULE_DESCRIPTION)

    raw = await file.read()
    result = import_tarball(
        tarball_bytes=raw,
        bot_schema=bot_schema,
        agent_schema=agent_schema,
        bot_config_path=settings.bot_config_path,
        agent_config_path=settings.agent_config_path,
        oauth_dest_path=drive_oauth.token_path,
        drive_schema=drive_schema,
        drive_config_path=settings.drive_config_path,
    )

    # Auto-restart bot and agent services to pick up imported config
    restart_results: dict[str, str] = {}
    for scope in ("bot", "agent"):
        try:
            resp = await client.restart(scope)
            restart_results[scope] = resp.get("status", "unknown")
        except Exception:
            logger.exception("Failed to restart %s after import", scope)
            restart_results[scope] = "restart_failed"

    return {**asdict(result), "restart_results": restart_results}
