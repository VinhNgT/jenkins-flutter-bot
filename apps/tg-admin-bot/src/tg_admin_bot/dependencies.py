"""Shared FastAPI dependencies for tg-admin-bot."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .manager import AdminBotManager


def get_manager(request: Request) -> AdminBotManager:
    """Inject the admin bot manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[AdminBotManager, Depends(get_manager)]
