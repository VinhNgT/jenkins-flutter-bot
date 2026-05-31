"""Configuration CRUD API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..dependencies import ManagerDep

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/schema")
async def get_schema(manager: ManagerDep) -> dict[str, Any]:
    """Return config field schemas aggregated from all modules."""
    return await manager.fetch_all_schemas()


@router.get("")
async def get_config(manager: ManagerDep) -> dict[str, Any]:
    """Return current config values with secrets stripped."""
    return await manager.get_config_for_ui()


@router.put("/{scope}")
async def save_config(
    scope: str, manager: ManagerDep, request: Request
) -> dict[str, Any]:
    """Save config for a scope using deep merge to preserve unmodified keys."""
    incoming: dict[str, Any] = await request.json()
    try:
        await manager.save_scope(scope, incoming)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok", "scope": scope}
