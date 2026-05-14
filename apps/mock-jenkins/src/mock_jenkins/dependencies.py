"""Shared FastAPI dependencies for mock-jenkins."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .manager import MockBuildManager


def get_manager(request: Request) -> MockBuildManager:
    """Inject the mock build manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[MockBuildManager, Depends(get_manager)]
