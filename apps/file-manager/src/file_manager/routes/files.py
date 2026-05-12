"""File upload/delete/cleanup routes — /api/files/*."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile

from ..control import StorageManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


def _mgr(request: Request) -> StorageManager:
    return request.app.state.manager


def _require_backend(mgr: StorageManager) -> None:
    if mgr.backend is None or mgr.config is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile) -> dict[str, Any]:
    """Upload a file to the storage backend.

    Accepts multipart form data with a ``file`` field.
    Returns ``{file_id, download_url}``.
    """
    mgr = _mgr(request)
    _require_backend(mgr)
    assert mgr.backend is not None  # for type narrowing
    assert mgr.config is not None

    # Write uploaded file to a temp location, then pass to backend
    suffix = os.path.splitext(file.filename or "file")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = await mgr.backend.upload(
            file_path=tmp_path,
            filename=file.filename or "upload",
            folder_name=mgr.config.drive_folder_name,
            client_id=mgr.config.drive_client_id,
            client_secret=mgr.config.drive_client_secret,
        )
        return {"file_id": result.file_id, "download_url": result.download_url}
    except Exception:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail="Upload failed")
    finally:
        os.unlink(tmp_path)


@router.delete("/{file_id}")
async def delete_file(request: Request, file_id: str) -> dict[str, str]:
    """Delete a single file by ID."""
    mgr = _mgr(request)
    _require_backend(mgr)
    assert mgr.backend is not None
    assert mgr.config is not None

    try:
        await mgr.backend.delete(
            file_id=file_id,
            client_id=mgr.config.drive_client_id,
            client_secret=mgr.config.drive_client_secret,
        )
        return {"status": "deleted"}
    except Exception:
        logger.exception("Delete failed for %s", file_id)
        raise HTTPException(status_code=500, detail="Delete failed")


@router.post("/cleanup")
async def cleanup_files(request: Request) -> dict[str, Any]:
    """Batch delete files. Expects ``{file_ids: [...]}``.

    Returns ``{deleted: [...], errors: [...]}``.
    """
    mgr = _mgr(request)
    _require_backend(mgr)
    assert mgr.backend is not None
    assert mgr.config is not None

    body = await request.json()
    file_ids: list[str] = body.get("file_ids", [])

    deleted: list[str] = []
    errors: list[dict[str, str]] = []

    for fid in file_ids:
        try:
            await mgr.backend.delete(
                file_id=fid,
                client_id=mgr.config.drive_client_id,
                client_secret=mgr.config.drive_client_secret,
            )
            deleted.append(fid)
        except Exception:
            logger.exception("Failed to delete %s", fid)
            errors.append({"file_id": fid, "error": "delete failed"})

    return {"deleted": deleted, "errors": errors}


@router.get("/status")
async def storage_status(request: Request) -> dict[str, Any]:
    """Return backend connection status."""
    mgr = _mgr(request)
    if mgr.backend is None or mgr.config is None:
        return {"connected": False, "detail": "not initialised"}
    return mgr.backend.status(
        client_id=mgr.config.drive_client_id,
        client_secret=mgr.config.drive_client_secret,
    )
