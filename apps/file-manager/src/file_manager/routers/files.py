"""File upload/delete/cleanup routes — /api/files/*."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile

from ..dependencies import ManagerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload")
async def upload_file(manager: ManagerDep, file: UploadFile) -> dict[str, Any]:
    """Upload a file to the storage backend.

    Accepts multipart form data with a ``file`` field.
    Returns ``{file_id, download_url}``.
    """
    if manager.backend is None or manager.config is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    # Write uploaded file to a temp location, then pass to backend
    suffix = os.path.splitext(file.filename or "file")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = await manager.backend.upload(
            file_path=tmp_path,
            filename=file.filename or "upload",
            folder_name=manager.config.drive_folder_name,
            client_id=manager.config.drive_client_id,
            client_secret=manager.config.drive_client_secret,
        )
        return {"file_id": result.file_id, "download_url": result.download_url}
    except Exception:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail="Upload failed")
    finally:
        os.unlink(tmp_path)


@router.delete("/{file_id}")
async def delete_file(manager: ManagerDep, file_id: str) -> dict[str, str]:
    """Delete a single file by ID."""
    if manager.backend is None or manager.config is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    try:
        await manager.backend.delete(
            file_id=file_id,
            client_id=manager.config.drive_client_id,
            client_secret=manager.config.drive_client_secret,
        )
        return {"status": "deleted"}
    except Exception:
        logger.exception("Delete failed for %s", file_id)
        raise HTTPException(status_code=500, detail="Delete failed")


@router.post("/cleanup")
async def cleanup_files(manager: ManagerDep, request: Request) -> dict[str, Any]:
    """Batch delete files. Expects ``{file_ids: [...]}``.

    Returns ``{deleted: [...], errors: [...]}``.
    """
    if manager.backend is None or manager.config is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    body = await request.json()
    file_ids: list[str] = body.get("file_ids", [])

    deleted: list[str] = []
    errors: list[dict[str, str]] = []

    for fid in file_ids:
        try:
            await manager.backend.delete(
                file_id=fid,
                client_id=manager.config.drive_client_id,
                client_secret=manager.config.drive_client_secret,
            )
            deleted.append(fid)
        except Exception:
            logger.exception("Failed to delete %s", fid)
            errors.append({"file_id": fid, "error": "delete failed"})

    return {"deleted": deleted, "errors": errors}


@router.get("/status")
async def storage_status(manager: ManagerDep) -> dict[str, Any]:
    """Return backend connection status."""
    if manager.backend is None or manager.config is None:
        return {"connected": False, "detail": "not initialised"}
    return manager.backend.status(
        client_id=manager.config.drive_client_id,
        client_secret=manager.config.drive_client_secret,
    )
