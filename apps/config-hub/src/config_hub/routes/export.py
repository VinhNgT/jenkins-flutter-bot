"""Config transfer routes — export/import configuration as tarballs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import Response

from ..manager import ConfigHubManager

router = APIRouter(prefix="/api", tags=["config-transfer"])


@router.get("/export/env")
async def export_env(request: Request) -> dict[str, Any]:
    """Generate per-service env file contents for preview."""
    manager: ConfigHubManager = request.app.state.manager
    return await manager.export_env()


@router.get("/export/tarball", response_model=None)
async def export_tarball(request: Request) -> Response:
    """Download a .tar.gz containing all config files."""
    manager: ConfigHubManager = request.app.state.manager
    tarball = await manager.export_tarball()
    return Response(
        content=tarball,
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=jfb-config.tar.gz"},
    )


@router.post("/import/tarball")
async def import_config_tarball(
    request: Request,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Import configuration from a .tar.gz export."""
    manager: ConfigHubManager = request.app.state.manager
    raw = await file.read()
    return await manager.import_tarball(raw)
