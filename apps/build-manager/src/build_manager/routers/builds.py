"""Build API routes — /api/builds/*.

Exposes the build lifecycle to frontends:
  - POST /api/builds/trigger           — start a new build
  - GET  /api/builds/pending           — list in-flight builds
  - GET  /api/builds/recent            — list completed builds
  - POST /api/builds/{id}/cancel       — cancel a pending build
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..dependencies import CoordinatorDep
from ..builds.jenkins_client import JenkinsTriggerError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/builds", tags=["builds"])


@router.post("/trigger")
async def trigger_build(coord: CoordinatorDep, request: Request) -> dict[str, Any]:
    """Trigger a new build.

    Expects JSON: ``{branch: "main", callback_url: "http://..."}``

    Returns ``{request_id, status: "queued"}``.
    """
    body = await request.json()
    branch = body.get("branch", "")
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")

    callback_url = body.get("callback_url", "")

    try:
        result = await coord.trigger_build(branch, frontend_callback_url=callback_url)
        return result
    except JenkinsTriggerError as exc:
        raise HTTPException(status_code=502, detail=exc.user_message) from exc


@router.get("/pending")
async def list_pending(coord: CoordinatorDep) -> dict[str, Any]:
    """List all in-flight builds."""
    pending = coord.tracker.list_pending()
    return {
        "builds": {
            k: {
                "branch": v.branch,
                "triggered_at": v.triggered_at,
            }
            for k, v in pending.items()
        }
    }


@router.get("/recent")
async def list_recent(coord: CoordinatorDep, count: int = 10) -> dict[str, Any]:
    """List recent completed builds."""
    builds = coord.tracker.recent_builds(count)
    return {
        "builds": [
            {
                "request_id": b.request_id,
                "branch": b.branch,
                "commit_hash": b.commit_hash,
                "result": b.result,
                "triggered_at": b.triggered_at,
                "completed_at": b.completed_at,
                "download_url": b.download_url,
            }
            for b in builds
        ]
    }


@router.post("/{request_id}/cancel")
async def cancel_build(coord: CoordinatorDep, request_id: str) -> dict[str, str]:
    """Cancel a pending build."""
    result = await coord.cancel_build(request_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Build not found")
    return result


@router.get("/status")
async def build_status(coord: CoordinatorDep) -> dict[str, Any]:
    """Return a summary of the build manager state."""
    return coord.tracker.to_dict()
