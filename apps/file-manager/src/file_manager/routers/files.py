"""File and build log routes — /api/files/*.

Manages build artifact uploads, build log queries, and file lifecycle
operations. The upload endpoint accepts build metadata alongside an
optional artifact file, recording both in the build log.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from ..dependencies import ManagerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

# Maximum upload size: 500 MB (APK files should never exceed this).
MAX_UPLOAD_SIZE = 500 * 1024 * 1024


# ------------------------------------------------------------------
# Build log endpoints
# ------------------------------------------------------------------


@router.post("/builds/record")
async def record_build(
    request: Request,
    manager: ManagerDep,
    request_id: str = Form(...),
    branch: str = Form(...),
    commit_hash: str = Form(""),
    result: str = Form(...),
    triggered_at: float = Form(...),
    completed_at: float = Form(...),
    file_size: int = Form(0),
    build_number: int = Form(0),
    file: UploadFile | None = None,
) -> dict[str, Any]:
    """Record a completed build, optionally uploading an artifact.

    Accepts multipart form data with build metadata fields and an optional
    ``file`` field. When a file is present (successful builds), it is stored
    in the backend and the download URL is recorded. When absent
    (failures/timeouts), only metadata is logged.

    Enforces retention — evicts the oldest records and deletes their
    backend files.
    """
    if manager.backend is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")
    if manager.build_log is None:
        raise HTTPException(status_code=503, detail="Build log not initialised")

    download_url = ""
    file_id = ""

    # Upload artifact if provided
    if file is not None:
        # Early rejection via Content-Length header (fast path).
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Upload too large (max {MAX_UPLOAD_SIZE // (1024 * 1024)} MB)",
            )

        content = await file.read()

        # Safety net: enforce after read() in case Content-Length was missing.
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Upload too large (max {MAX_UPLOAD_SIZE // (1024 * 1024)} MB)",
            )

        try:
            upload_result = await manager.backend.upload(
                content, file.filename or "upload"
            )
            download_url = upload_result.download_url
            file_id = upload_result.file_id
        except Exception:
            logger.exception("Upload failed")
            raise HTTPException(status_code=500, detail="Upload failed")

    # Record in build log and enforce retention
    evicted = manager.build_log.record(
        request_id=request_id,
        branch=branch,
        commit_hash=commit_hash,
        result=result,
        triggered_at=triggered_at,
        completed_at=completed_at,
        download_url=download_url,
        file_id=file_id,
        file_size=file_size,
        build_number=build_number,
    )

    # Delete backend files for evicted records (best-effort)
    for record in evicted:
        if record.file_id:
            try:
                await manager.backend.delete(record.file_id)
                logger.info(
                    "Evicted build %s — deleted file %s",
                    record.request_id,
                    record.file_id,
                )
            except Exception:
                logger.exception(
                    "Failed to delete file %s for evicted build %s",
                    record.file_id,
                    record.request_id,
                )

    return {
        "status": "recorded",
        "file_id": file_id,
        "download_url": download_url,
    }


@router.get("/builds/recent")
async def get_recent_builds(
    manager: ManagerDep, count: int = 5
) -> dict[str, Any]:
    """Return recent completed build records, newest first."""
    if manager.build_log is None:
        raise HTTPException(status_code=503, detail="Build log not initialised")

    records = manager.build_log.recent(count)
    return {
        "builds": [
            {
                "request_id": r.request_id,
                "branch": r.branch,
                "commit_hash": r.commit_hash,
                "result": r.result,
                "triggered_at": r.triggered_at,
                "completed_at": r.completed_at,
                "download_url": r.download_url,
                "file_size": r.file_size,
                "build_number": r.build_number,
            }
            for r in records
        ]
    }


# ------------------------------------------------------------------
# File lifecycle endpoints
# ------------------------------------------------------------------


@router.delete("/{file_id}")
async def delete_file(manager: ManagerDep, file_id: str) -> dict[str, str]:
    """Delete a single file by ID and remove its build log record."""
    if manager.backend is None:
        raise HTTPException(status_code=503, detail="Storage backend not initialised")

    try:
        await manager.backend.delete(file_id)
    except Exception:
        logger.exception("Delete failed for %s", file_id)
        raise HTTPException(status_code=500, detail="Delete failed")

    if manager.build_log is not None:
        manager.build_log.remove_by_file_id(file_id)

    return {"status": "deleted"}


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
            if manager.build_log is not None:
                manager.build_log.remove_by_file_id(fid)
        except Exception:
            logger.exception("Failed to delete %s", fid)
            errors.append({"file_id": fid, "error": "delete failed"})

    return {"deleted": deleted, "errors": errors}


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
