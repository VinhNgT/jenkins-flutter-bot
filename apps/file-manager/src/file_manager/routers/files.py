"""File upload/delete/cleanup/download routes — /api/files/*."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import Response

from ..dependencies import ManagerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

# Maximum upload size: 500 MB (APK files should never exceed this).
MAX_UPLOAD_SIZE = 500 * 1024 * 1024


@router.post("/upload")
async def upload_file(
    request: Request, manager: ManagerDep, file: UploadFile,
) -> dict[str, Any]:
    """Upload a file to the storage backend.

    Accepts multipart form data with a ``file`` field.
    Returns ``{file_id, download_url}``.
    """
    if manager.backend is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    # Early rejection via Content-Length header (fast path).
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Upload too large (max {MAX_UPLOAD_SIZE // (1024 * 1024)} MB)",
        )

    content = await file.read()

    # Safety net: enforce after read() in case Content-Length was missing/spoofed.
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Upload too large (max {MAX_UPLOAD_SIZE // (1024 * 1024)} MB)",
        )

    try:
        result = await manager.backend.upload(content, file.filename or "upload")
        return {"file_id": result.file_id, "download_url": result.download_url}
    except Exception:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail="Upload failed")


@router.delete("/{file_id}")
async def delete_file(manager: ManagerDep, file_id: str) -> dict[str, str]:
    """Delete a single file by ID."""
    if manager.backend is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    try:
        await manager.backend.delete(file_id)
        return {"status": "deleted"}
    except Exception:
        logger.exception("Delete failed for %s", file_id)
        raise HTTPException(status_code=500, detail="Delete failed")


@router.post("/cleanup")
async def cleanup_files(manager: ManagerDep, request: Request) -> dict[str, Any]:
    """Batch delete files. Expects ``{file_ids: [...]}``.

    Returns ``{deleted: [...], errors: [...]}``.
    """
    if manager.backend is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    body = await request.json()
    file_ids: list[str] = body.get("file_ids", [])

    deleted: list[str] = []
    errors: list[dict[str, str]] = []

    for fid in file_ids:
        try:
            await manager.backend.delete(fid)
            deleted.append(fid)
        except Exception:
            logger.exception("Failed to delete %s", fid)
            errors.append({"file_id": fid, "error": "delete failed"})

    return {"deleted": deleted, "errors": errors}


@router.get("/status")
async def storage_status(manager: ManagerDep) -> dict[str, Any]:
    """Return backend connection status."""
    if manager.backend is None:
        return {"connected": False, "detail": "not initialised"}
    return await manager.backend.status()


@router.get("/{file_id}/download")
async def download_file(manager: ManagerDep, file_id: str) -> Response:
    """Download a file from ephemeral storage.

    Only available when the ephemeral backend is active.
    Google Drive files are downloaded directly from Drive URLs.
    """
    ephemeral = manager.ephemeral_backend
    if ephemeral is None:
        raise HTTPException(
            status_code=404,
            detail="Download endpoint is only available in ephemeral mode",
        )

    stored = ephemeral.get(file_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="File not found")

    return Response(
        content=stored.data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{stored.filename}"',
        },
    )
