"""Shared FastAPI dependencies for tg-jenkins-bot."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .manager import BotManager


def get_manager(request: Request) -> BotManager:
    """Inject the bot manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[BotManager, Depends(get_manager)]
