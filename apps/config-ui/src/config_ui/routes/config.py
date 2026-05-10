"""Configuration CRUD API routes."""

from __future__ import annotations

from typing import Any

from config_schema import deep_merge
from fastapi import APIRouter, Request

from ..config_store import (
    DRIVE_SECRET_FIELDS,
    clean_secrets_from_payload,
    extract_secret_fields,
    load_json,
    secrets_set,
    strip_secrets,
    write_json,
)
from ..schema import (
    DRIVE_FIELDS,
    MODULE_DESCRIPTION,
    MODULE_TITLE,
    PROJECT_FIELDS,
    PROJECT_MODULE_DESCRIPTION,
    PROJECT_MODULE_TITLE,
    serialize_schema,
)
from stack_manager import ServiceClient
from ..settings import Settings

router = APIRouter(prefix="/api/config", tags=["config"])


async def _fetch_schemas(
    client: ServiceClient,
) -> dict[str, dict[str, Any] | None]:
    """Fetch schemas from bot and agent services."""
    return {
        "bot": await client.schema("bot"),
        "agent": await client.schema("agent"),
    }


@router.get("/schema")
async def get_schema(request: Request) -> dict[str, Any]:
    """Return config field schemas aggregated from all modules."""
    client: ServiceClient = request.app.state.service_client
    schemas = await _fetch_schemas(client)
    schemas["drive"] = serialize_schema(DRIVE_FIELDS, MODULE_TITLE, MODULE_DESCRIPTION)
    schemas["project"] = serialize_schema(
        PROJECT_FIELDS, PROJECT_MODULE_TITLE, PROJECT_MODULE_DESCRIPTION
    )
    return schemas


@router.get("")
async def get_config(request: Request) -> dict[str, Any]:
    """Return current config values with secrets stripped."""
    settings: Settings = request.app.state.settings
    client: ServiceClient = request.app.state.service_client

    # Fetch schemas to determine which fields are secrets
    schemas = await _fetch_schemas(client)
    bot_secrets = extract_secret_fields(schemas.get("bot"))
    agent_secrets = extract_secret_fields(schemas.get("agent"))

    raw = {
        "bot": load_json(settings.bot_config_path),
        "agent": load_json(settings.agent_config_path),
        "drive": load_json(settings.drive_config_path),
        "project": load_json(settings.project_config_path),
    }

    return {
        "bot": strip_secrets(raw["bot"], bot_secrets),
        "agent": strip_secrets(raw["agent"], agent_secrets),
        "drive": strip_secrets(raw["drive"], DRIVE_SECRET_FIELDS),
        "project": raw["project"],  # no secret fields in project scope
        "_secrets_set": {
            "bot": secrets_set(raw["bot"], bot_secrets),
            "agent": secrets_set(raw["agent"], agent_secrets),
            "drive": secrets_set(raw["drive"], DRIVE_SECRET_FIELDS),
        },
    }


@router.put("/{scope}")
async def save_config(scope: str, request: Request) -> dict[str, Any]:
    """Save config for a scope using deep merge to preserve unmodified keys."""
    settings: Settings = request.app.state.settings
    client: ServiceClient = request.app.state.service_client

    path_map = {
        "bot": settings.bot_config_path,
        "agent": settings.agent_config_path,
        "drive": settings.drive_config_path,
        "project": settings.project_config_path,
    }
    path = path_map.get(scope)
    if path is None:
        return {"error": f"Unknown scope: {scope}"}

    # Determine secret fields for this scope
    if scope == "drive":
        secret_fields = DRIVE_SECRET_FIELDS
    elif scope == "project":
        secret_fields = ()  # project has no secret fields
    else:
        schema = await client.schema(scope)
        secret_fields = extract_secret_fields(schema)

    incoming: dict[str, Any] = await request.json()
    cleaned = clean_secrets_from_payload(incoming, secret_fields)

    existing = load_json(path)
    merged = deep_merge(existing, cleaned)
    write_json(path, merged)

    return {"status": "ok", "scope": scope}
