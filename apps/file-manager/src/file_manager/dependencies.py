"""Shared FastAPI dependencies for file-manager."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from .manager import StorageManager


def get_manager(request: Request) -> StorageManager:
    """Inject the storage manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[StorageManager, Depends(get_manager)]


def require_backend(manager: ManagerDep) -> StorageManager:
    """Guard: raise 503 if the storage backend is not initialised."""
    if manager.backend is None or manager.config is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")
    return manager


RequireBackendDep = Annotated[StorageManager, Depends(require_backend)]
