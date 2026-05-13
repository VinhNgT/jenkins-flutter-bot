"""Build API routes — /api/builds/*.

Exposes the build lifecycle to frontends:
  - POST /api/builds/trigger     — start a new build
  - POST /api/builds/webhook     — receive build-complete callback
  - GET  /api/builds/pending     — list in-flight builds
  - GET  /api/builds/recent      — list completed builds
  - POST /api/builds/{id}/cancel — cancel a pending build
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile

from .jenkins_client import JenkinsTriggerError
from .orchestrator import BuildOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/builds", tags=["builds"])


def _orchestrator(request: Request) -> BuildOrchestrator:
    return request.app.state.orchestrator


@router.post("/trigger")
async def trigger_build(request: Request) -> dict[str, Any]:
    """Trigger a new build.

    Expects JSON: ``{branch: "main", callback_url: "http://..."}``

    Returns ``{request_id, status: "queued"}``.
    """
    body = await request.json()
    branch = body.get("branch", "")
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")

    callback_url = body.get("callback_url", "")
    orch = _orchestrator(request)

    try:
        result = await orch.trigger_build(
            branch, frontend_callback_url=callback_url
        )
        return result
    except JenkinsTriggerError as exc:
        raise HTTPException(status_code=502, detail=exc.user_message) from exc


@router.post("/webhook")
async def build_webhook(
    request: Request,
    metadata: str | None = None,
    artifact: UploadFile | None = None,
) -> dict[str, str]:
    """Receive a build-complete callback from the Jenkins agent.

    Expects multipart form data with:
      - ``metadata``: JSON string with build result info
      - ``artifact``: optional uploaded APK file (on success)
    """
    import json

    # Parse metadata from form or body
    if metadata:
        meta = json.loads(metadata)
    else:
        # Fall back to reading the raw form
        form = await request.form()
        meta_field = form.get("metadata")
        if meta_field is None:
            return {"status": "ignored"}
        meta = json.loads(str(meta_field))
        artifact = form.get("artifact")  # type: ignore[assignment]

    artifact_path: str | None = None

    if artifact is not None and hasattr(artifact, "read"):
        suffix = os.path.splitext(artifact.filename or "file")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await artifact.read())
            artifact_path = tmp.name

    orch = _orchestrator(request)

    try:
        return await orch.handle_webhook(meta, artifact_path)
    finally:
        # Clean up temp file if upload failed or was handled
        if artifact_path and os.path.exists(artifact_path):
            os.unlink(artifact_path)


@router.get("/pending")
async def list_pending(request: Request) -> dict[str, Any]:
    """List all in-flight builds."""
    orch = _orchestrator(request)
    pending = orch.tracker.list_pending()
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
async def list_recent(request: Request, count: int = 10) -> dict[str, Any]:
    """List recent completed builds."""
    orch = _orchestrator(request)
    builds = orch.tracker.recent_builds(count)
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
async def cancel_build(request: Request, request_id: str) -> dict[str, str]:
    """Cancel a pending build."""
    orch = _orchestrator(request)
    result = await orch.cancel_build(request_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Build not found")
    return result


@router.get("/status")
async def build_status(request: Request) -> dict[str, Any]:
    """Return a summary of the build orchestrator state."""
    orch = _orchestrator(request)
    return orch.tracker.to_dict()
