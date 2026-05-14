"""Shared FastAPI dependencies for build-manager."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from .builds.coordinator import BuildCoordinator
from .manager import BuildManager


def get_manager(request: Request) -> BuildManager:
    """Inject the build manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[BuildManager, Depends(get_manager)]


def get_coordinator(manager: ManagerDep) -> BuildCoordinator:
    """Inject the build coordinator — requires manager to be running.

    This is a sub-dependency chained from ManagerDep.  It replaces the
    old ``_inject_coordinator`` middleware with a proper FastAPI
    ``Depends()`` guard.
    """
    if not manager.running:
        raise HTTPException(status_code=503, detail="Build manager not running")
    return manager.coordinator


CoordinatorDep = Annotated[BuildCoordinator, Depends(get_coordinator)]
