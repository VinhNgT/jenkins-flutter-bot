"""Jenkinsfile generation API route."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..dependencies import ManagerDep

router = APIRouter(prefix="/api", tags=["jenkinsfile"])


@router.get("/jenkinsfile")
async def get_jenkinsfile(manager: ManagerDep) -> dict[str, Any]:
    """Generate a Jenkinsfile pipeline script from current config."""
    return await manager.get_jenkinsfile()
