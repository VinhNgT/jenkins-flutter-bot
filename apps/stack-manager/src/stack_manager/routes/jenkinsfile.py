"""Jenkinsfile generation API route."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..manager import StackManager

router = APIRouter(prefix="/api", tags=["jenkinsfile"])


@router.get("/jenkinsfile")
async def get_jenkinsfile(request: Request) -> dict[str, Any]:
    """Generate a Jenkinsfile pipeline script from current config."""
    manager: StackManager = request.app.state.manager
    return manager.get_jenkinsfile()
