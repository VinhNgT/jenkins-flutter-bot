"""Shared FastAPI dependencies for file-manager."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .manager import StorageManager


def get_manager(request: Request) -> StorageManager:
    """Inject the storage manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[StorageManager, Depends(get_manager)]
