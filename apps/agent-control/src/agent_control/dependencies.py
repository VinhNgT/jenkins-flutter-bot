"""Shared FastAPI dependencies for agent-control."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .manager import AgentManager


def get_manager(request: Request) -> AgentManager:
    """Inject the agent manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[AgentManager, Depends(get_manager)]
