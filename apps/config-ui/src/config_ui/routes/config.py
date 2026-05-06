"""Configuration CRUD API routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..config_store import (
    SCOPE_DEFAULTS,
    SCOPE_REQUIRED_FIELDS,
    SCOPE_SECRET_FIELDS,
    clean_secrets_from_payload,
    deep_merge,
    load_json,
    secrets_set,
    strip_secrets,
    write_json,
)
from ..settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


def _scope_path(settings: Settings, scope: str) -> Any:
    """Return the config file path for a given scope."""
    paths = {
        "bot": settings.bot_config_path,
        "agent": settings.agent_config_path,
        "ui": settings.ui_config_path,
    }
    path = paths.get(scope)
    if path is None and scope not in paths:
        raise HTTPException(status_code=404, detail=f"Unknown scope: {scope}")
    return path


@router.get("")
async def get_config(request: Request) -> dict[str, Any]:
    """Return all config with secrets stripped + _secrets_set flags.

    Response shape::

        {
          "bot": {...},
          "agent": {...},
          "ui": {...},
          "_secrets_set": {
            "bot": {"telegram.bot_token": true, ...},
            "agent": {"agent.secret": false},
            "ui": {"drive.client_secret": true}
          }
        }
    """
    settings: Settings = request.app.state.settings
    raw = {
        "bot": load_json(settings.bot_config_path),
        "agent": load_json(settings.agent_config_path),
        "ui": load_json(settings.ui_config_path),
    }
    return {
        "bot": strip_secrets(raw["bot"], SCOPE_SECRET_FIELDS["bot"]),
        "agent": strip_secrets(raw["agent"], SCOPE_SECRET_FIELDS["agent"]),
        "ui": strip_secrets(raw["ui"], SCOPE_SECRET_FIELDS["ui"]),
        "_secrets_set": {
            scope: secrets_set(raw[scope], fields)
            for scope, fields in SCOPE_SECRET_FIELDS.items()
        },
        "_defaults": SCOPE_DEFAULTS,
        "_required": SCOPE_REQUIRED_FIELDS,
    }


@router.post("/{scope}")
async def save_scoped_config(
    request: Request, scope: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Save config for a single scope (bot, agent, or ui).

    The payload is the config data for that scope only — not wrapped
    in a scope key.  Secret fields that are None/empty are stripped
    before merge so existing values are preserved.
    """
    settings: Settings = request.app.state.settings
    path = _scope_path(settings, scope)

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid config payload")

    secret_fields = SCOPE_SECRET_FIELDS.get(scope, ())
    cleaned = clean_secrets_from_payload(payload, secret_fields)
    existing = load_json(path)
    merged = deep_merge(existing, cleaned)
    write_json(path, merged)
    logger.info("Saved %s config", scope)
    return {"saved": True, "scope": scope}


@router.post("")
async def save_all_config(
    request: Request, payload: dict[str, Any]
) -> dict[str, Any]:
    """Save all scopes at once.

    Payload shape: ``{"bot": {...}, "agent": {...}, "ui": {...}}``
    """
    settings: Settings = request.app.state.settings

    for scope in ("bot", "agent", "ui"):
        incoming = payload.get(scope, {})
        if not isinstance(incoming, dict):
            raise HTTPException(
                status_code=400, detail=f"Invalid config payload for {scope}"
            )
        path = _scope_path(settings, scope)
        secret_fields = SCOPE_SECRET_FIELDS.get(scope, ())
        cleaned = clean_secrets_from_payload(incoming, secret_fields)
        existing = load_json(path)
        merged = deep_merge(existing, cleaned)
        write_json(path, merged)

    logger.info("Saved all config scopes")
    return {"saved": True}
