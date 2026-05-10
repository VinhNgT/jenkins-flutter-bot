"""Version API route — exposes the installed package version."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/version")
async def get_version() -> dict[str, str]:
    """Return the installed config-ui package version."""
    try:
        v = version("config-ui")
    except PackageNotFoundError:
        v = "unknown"
    return {"version": v}
