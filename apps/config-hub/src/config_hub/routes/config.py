"""Configuration CRUD API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..manager import ConfigHubManager

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/schema")
async def get_schema(request: Request) -> dict[str, Any]:
    """Return config field schemas aggregated from all modules."""
    manager: ConfigHubManager = request.app.state.manager
    return await manager.fetch_all_schemas()


@router.get("")
async def get_config(request: Request) -> dict[str, Any]:
    """Return current config values with secrets stripped."""
    manager: ConfigHubManager = request.app.state.manager
    return await manager.get_config_for_ui()


@router.put("/{scope}")
async def save_config(scope: str, request: Request) -> dict[str, Any]:
    """Save config for a scope using deep merge to preserve unmodified keys."""
    manager: ConfigHubManager = request.app.state.manager

    if scope not in {"bot", "agent", "storage", "orchestrator"}:
        return {"error": f"Unknown scope: {scope}"}

    incoming: dict[str, Any] = await request.json()
    await manager.save_scope(scope, incoming)
    return {"status": "ok", "scope": scope}
