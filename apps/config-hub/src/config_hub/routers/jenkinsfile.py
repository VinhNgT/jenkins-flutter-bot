"""Jenkinsfile generation API route."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..dependencies import ManagerDep

router = APIRouter(prefix="/api/webapp-admin", tags=["jenkinsfile"])


@router.get("/jenkinsfile")
async def get_jenkinsfile(
    manager: ManagerDep,
    discard_builds: bool = True,
    clean_workspace: bool = False,
    shallow_clone: bool = True,
    repo_url: str | None = None,
    credentials_id: str | None = None,
) -> dict[str, Any]:
    """Generate a Jenkinsfile pipeline script from current config."""
    return await manager.get_jenkinsfile(
        discard_builds=discard_builds,
        clean_workspace=clean_workspace,
        shallow_clone=shallow_clone,
        repo_url=repo_url,
        credentials_id=credentials_id,
    )
