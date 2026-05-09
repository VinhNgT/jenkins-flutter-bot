"""Configuration CRUD API routes."""

from __future__ import annotations

from typing import Any

from config_schema import deep_merge
from fastapi import APIRouter, Request

from ..config_store import (
    UI_SECRET_FIELDS,
    clean_secrets_from_payload,
    extract_secret_fields,
    load_json,
    secrets_set,
    strip_secrets,
    write_json,
)
from ..schema import MODULE_DESCRIPTION, MODULE_TITLE, UI_FIELDS, serialize_schema
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
    schemas["ui"] = serialize_schema(UI_FIELDS, MODULE_TITLE, MODULE_DESCRIPTION)
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
        "ui": load_json(settings.ui_config_path),
    }

    return {
        "bot": strip_secrets(raw["bot"], bot_secrets),
        "agent": strip_secrets(raw["agent"], agent_secrets),
        "ui": strip_secrets(raw["ui"], UI_SECRET_FIELDS),
        "_secrets_set": {
            "bot": secrets_set(raw["bot"], bot_secrets),
            "agent": secrets_set(raw["agent"], agent_secrets),
            "ui": secrets_set(raw["ui"], UI_SECRET_FIELDS),
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
        "ui": settings.ui_config_path,
    }
    path = path_map.get(scope)
    if path is None:
        return {"error": f"Unknown scope: {scope}"}

    # Determine secret fields for this scope
    if scope == "ui":
        secret_fields = UI_SECRET_FIELDS
    else:
        schema = await client.schema(scope)
        secret_fields = extract_secret_fields(schema)

    incoming: dict[str, Any] = await request.json()
    cleaned = clean_secrets_from_payload(incoming, secret_fields)

    existing = load_json(path)
    merged = deep_merge(existing, cleaned)
    write_json(path, merged)

    return {"status": "ok", "scope": scope}
