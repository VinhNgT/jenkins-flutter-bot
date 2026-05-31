"""Shared FastAPI dependencies for service-hub."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .manager import ServiceHubManager


def get_manager(request: Request) -> ServiceHubManager:
    """Inject the service-hub manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[ServiceHubManager, Depends(get_manager)]
