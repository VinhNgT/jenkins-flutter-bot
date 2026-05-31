"""Version API route — exposes the installed package version."""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/version")
async def get_version() -> dict[str, str]:
    """Return the installed service-hub package version."""
    try:
        v = version("service-hub")
        # Python packaging normalizes version strings according to PEP 440
        # (e.g. "0.3.2-dev.2" becomes "0.3.2.dev2"). We map PEP 440 pre-releases
        # back to the exact human-authored format in pyproject.toml.
        v = re.sub(r"^(\d+\.\d+\.\d+)\.(dev|rc)(\d+)$", r"\1-\2.\3", v)
    except PackageNotFoundError:
        v = "unknown"
    return {"version": v}
