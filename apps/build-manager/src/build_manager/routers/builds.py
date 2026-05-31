"""Build API routes — /api/builds/*.

Exposes the build lifecycle to frontends:
  - POST /api/builds/trigger           — start a new build
  - GET  /api/builds/pending           — list in-flight builds
  - POST /api/builds/{id}/cancel       — cancel a pending build
  - GET  /api/builds/status            — pending build summary
  - GET  /api/builds/stream            — SSE stream of active + recent builds

Completed build history is served by file-manager
(``GET /api/files/builds/recent``).
"""

from __future__ import annotations

import logging
import asyncio
import hashlib
import json
import httpx
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ..dependencies import CoordinatorDep
from ..builds.jenkins_client import JenkinsTriggerError
from ..builds.coordinator import DuplicateBuildError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/builds", tags=["builds"])


@router.post("/trigger")
async def trigger_build(coord: CoordinatorDep, request: Request) -> dict[str, Any]:
    """Trigger a new build.

    Expects JSON: ``{branch: "main", callback_url: "http://...", app_name: "..."}``

    Returns ``{request_id, status: "queued"}``.
    """
    body = await request.json()
    branch = body.get("branch", "")
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")

    callback_url = body.get("callback_url", "")
    app_name = body.get("app_name", None)
    label = body.get("label", "")
    triggered_by = body.get("triggered_by", "")
    triggered_by_id = body.get("triggered_by_id", 0)
    notify = body.get("notify", True)
    chat_id = body.get("chat_id", 0)

    try:
        result = await coord.trigger_build(
            branch,
            frontend_callback_url=callback_url,
            app_name=app_name,
            label=label,
            triggered_by=triggered_by,
            triggered_by_id=triggered_by_id,
            notify=notify,
            chat_id=chat_id,
        )
        return result
    except DuplicateBuildError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
                "label": v.label,
                "triggered_by": v.triggered_by,
                "triggered_by_id": v.triggered_by_id,
                "notify": v.notify,
                "estimated_duration": v.estimated_duration,
                "chat_id": v.chat_id,
            }
            for k, v in pending.items()
        }
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


@router.get("/recent")
async def recent_builds(coord: CoordinatorDep, count: int = 5) -> dict[str, Any]:
    """Fetch completed build history from file-manager."""
    try:
        url = f"{coord._file_manager_url}/api/files/builds/recent?count={count}"
        resp = await coord._http.get(url)
        if resp.status_code == 200:
            return resp.json()
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Failed to fetch recent builds from file-manager: {resp.text}",
        )
    except httpx.HTTPError as exc:
        logger.exception("Failed to connect to file-manager")
        raise HTTPException(
            status_code=502,
            detail=f"Bad Gateway: file-manager is unreachable: {exc}",
        )


@router.get("/stream", response_class=EventSourceResponse)
async def stream_builds(
    request: Request,
    coord: CoordinatorDep,
):
    """Stream active builds and recent builds using Server-Sent Events (SSE)."""
    event = asyncio.Event()
    coord.tracker.add_listener(event)
    last_sent_active_hash = None
    last_sent_recent_hash = None

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected from build-manager")
                break

            # Fetch active builds
            pending = coord.tracker.list_pending()
            active_builds = [
                {
                    "request_id": v.request_id,
                    "branch": v.branch,
                    "triggered_at": v.triggered_at,
                    "queue_id": v.queue_id,
                    "app_name": v.app_name,
                    "label": v.label,
                    "triggered_by": v.triggered_by,
                    "triggered_by_id": v.triggered_by_id,
                    "notify": v.notify,
                    "estimated_duration": v.estimated_duration,
                    "chat_id": v.chat_id,
                }
                for v in pending.values()
            ]

            # Fetch recent builds from file-manager
            recent_builds = []
            try:
                url = f"{coord._file_manager_url}/api/files/builds/recent?count=5"
                resp = await coord._http.get(url)
                if resp.status_code == 200:
                    recent_builds = resp.json().get("builds", [])
            except Exception:
                logger.warning("Failed to fetch recent builds for SSE stream in build-manager")

            active_str = json.dumps(active_builds, sort_keys=True)
            active_hash = hashlib.sha256(active_str.encode()).hexdigest()

            recent_str = json.dumps(recent_builds, sort_keys=True)
            recent_hash = hashlib.sha256(recent_str.encode()).hexdigest()

            if last_sent_active_hash is None or active_hash != last_sent_active_hash:
                last_sent_active_hash = active_hash
                yield ServerSentEvent(data=active_builds, event="builds")

            if last_sent_recent_hash is None or recent_hash != last_sent_recent_hash:
                last_sent_recent_hash = recent_hash
                yield ServerSentEvent(data=recent_builds, event="recent")

            try:
                await asyncio.wait_for(event.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                pass

            event.clear()
    except asyncio.CancelledError:
        logger.info("SSE streaming cancelled in build-manager")
        raise
    finally:
        coord.tracker.remove_listener(event)
