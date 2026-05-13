"""Jenkinsfile generation API route."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..manager import ConfigHubManager

router = APIRouter(prefix="/api", tags=["jenkinsfile"])


@router.get("/jenkinsfile")
async def get_jenkinsfile(request: Request) -> dict[str, Any]:
    """Generate a Jenkinsfile pipeline script from current config."""
    manager: ConfigHubManager = request.app.state.manager
    return await manager.get_jenkinsfile()
