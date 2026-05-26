"""Control routes — /control/*.

Standard service lifecycle and config management endpoints.
The schema endpoint adapts based on the active storage backend.
"""

from __future__ import annotations

from typing import Any

from config_core import get_frontend_schema, read_masked_config, save_config_with_merge
from fastapi import APIRouter, Request

from ..config import StorageSettings, _DEFAULT_CONFIG_PATH
from ..dependencies import ManagerDep

router = APIRouter(prefix="/control", tags=["control"])


@router.get("/status")
async def get_status(manager: ManagerDep) -> dict[str, Any]:
    """Return storage manager status (includes backend_type)."""
    return manager.status()


@router.post("/start")
async def start_manager(manager: ManagerDep) -> dict[str, Any]:
    """Start the storage manager."""
    await manager.start()
    return manager.status()


@router.post("/stop")
async def stop_manager(manager: ManagerDep) -> dict[str, Any]:
    """Stop the storage manager."""
    await manager.stop()
    return manager.status()


@router.post("/restart")
async def restart_manager(manager: ManagerDep) -> dict[str, Any]:
    """Restart the storage manager with fresh config."""
    await manager.restart()
    return manager.status()


@router.get("/schema")
async def get_schema(manager: ManagerDep) -> dict[str, Any]:
    """Return the file storage config field schema.

    In ephemeral mode, returns a minimal schema with no editable fields
    since Drive configuration is irrelevant. In Google Drive mode,
    returns the full schema with OAuth credential fields.
    """
    if manager.backend_type == "ephemeral":
        return {
            "title": "File Storage Configuration",
            "description": (
                "Storage is running in <strong>ephemeral mode</strong> — files are"
                " stored in memory and will be lost when the service restarts."
                " This is intended for development and testing."
                " To use persistent storage, set"
                " <code>STORAGE_BACKEND=google_drive</code>."
            ),
            "fields": [],
        }

    return get_frontend_schema(
        StorageSettings,
        title="File Storage Configuration",
        description=(
            "Configures the storage backend used for uploading build artifacts."
            " The current implementation uses Google Drive — enter your OAuth"
            " credentials below, then connect via the dashboard."
        ),
    )


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """Return current config values with secrets masked."""
    return read_masked_config(StorageSettings, _DEFAULT_CONFIG_PATH)


@router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    payload = await request.json()
    save_config_with_merge(StorageSettings, _DEFAULT_CONFIG_PATH, payload)
    return {"status": "saved"}
