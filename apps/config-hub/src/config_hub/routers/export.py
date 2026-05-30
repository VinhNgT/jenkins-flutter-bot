"""Config transfer routes — export/import configuration as tarballs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..dependencies import ManagerDep

router = APIRouter(prefix="/api/webapp-admin", tags=["config-transfer"])

# Maximum import tarball size: 5 MB (config files are tiny).
MAX_IMPORT_SIZE = 5 * 1024 * 1024


@router.get("/export/env")
async def export_env(manager: ManagerDep) -> dict[str, Any]:
    """Generate per-service env file contents for preview."""
    return await manager.export_env()


@router.get("/export/tarball", response_model=None)
async def export_tarball(manager: ManagerDep) -> Response:
    """Download a .tar.gz containing all config files."""
    tarball = await manager.export_tarball()
    return Response(
        content=tarball,
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=jfb-config.tar.gz"},
    )


@router.post("/import/tarball")
async def import_config_tarball(
    manager: ManagerDep,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Import configuration from a .tar.gz export."""
    raw = await file.read()

    if len(raw) > MAX_IMPORT_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Import too large (max {MAX_IMPORT_SIZE // (1024 * 1024)} MB)",
        )

    return await manager.import_tarball(raw)
