"""Jenkins API mock routes.

Implements only the endpoints that JenkinsClient actually uses:
  - GET  /job/{name}/api/json              — connection check + build history
  - POST /job/{name}/buildWithParameters   — trigger a build
  - GET  /job/{name}/{num}/api/json        — per-build status + artifacts
  - GET  /job/{name}/{num}/artifact/{path} — artifact download
  - POST /queue/cancelItem                 — cancel a queued build
  - GET  /queue/item/{id}/api/json         — queue item info
  - POST /job/{name}/{number}/stop         — stop a running build
  - GET  /crumbIssuer/api/json             — CSRF crumb
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query, Request, Response

from ..dependencies import ManagerDep
from ..manager import DUMMY_APK, MockBuild

router = APIRouter()


@router.get("/")
async def root(manager: ManagerDep) -> dict[str, str]:
    """Health check."""
    return {
        "status": "mock-jenkins running",
        "build_delay": f"{manager.config.mock_build_delay}s",
    }


# ---------------------------------------------------------------------------
# Jenkins API: job info + build history
# ---------------------------------------------------------------------------


@router.get("/job/{job_name}/api/json")
async def job_api(manager: ManagerDep, job_name: str, tree: str = "") -> dict[str, Any]:
    """Serve job info and build history.

    When tree contains 'builds', return build history.
    When tree contains 'name', return just the job name (connection check).
    """
    if "name" in tree and "builds" not in tree:
        # Connection check — GET /job/{name}/api/json?tree=name
        return {
            "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
            "name": job_name,
        }

    # Build history query
    builds_json: list[dict[str, Any]] = []
    for b in reversed(manager.build_history[-20:]):
        actions: list[dict[str, Any]] = [
            {
                "parameters": [
                    {"name": "BRANCH", "value": b.branch},
                    {"name": "BOT_REQUEST_ID", "value": b.request_id},
                ]
            },
        ]

        # Add lastBuiltRevision when build is complete (simulates Git plugin)
        if not b.building and b.commit_hash:
            actions.append({
                "lastBuiltRevision": {"SHA1": b.commit_hash},
            })

        builds_json.append(
            {
                "_class": "org.jenkinsci.plugins.workflow.job.WorkflowRun",
                "number": b.build_number,
                "result": b.result if not b.building else None,
                "building": b.building,
                "timestamp": int(b.timestamp * 1000),  # s → ms
                "duration": b.duration_ms,
                "actions": actions,
            }
        )

    return {
        "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
        "name": job_name,
        "builds": builds_json,
    }


# ---------------------------------------------------------------------------
# Jenkins API: trigger build
# ---------------------------------------------------------------------------


@router.post("/job/{job_name}/buildWithParameters")
async def trigger_build(
    manager: ManagerDep,
    job_name: str,
    request: Request,
    BRANCH: str = Query(default="main"),
    BOT_REQUEST_ID: str = Query(default=""),
) -> Response:
    """Accept a parameterised build trigger — mimics Jenkins 201 response."""
    import logging

    logger = logging.getLogger(__name__)

    queue_id, build_number = manager.allocate_ids()

    build = MockBuild(
        queue_id=queue_id,
        build_number=build_number,
        branch=BRANCH,
        request_id=BOT_REQUEST_ID,
    )

    manager.register_build(build)

    logger.info(
        "Build triggered: #%d queue_id=%d branch=%s request_id=%s",
        build_number,
        queue_id,
        BRANCH,
        BOT_REQUEST_ID[:8] if BOT_REQUEST_ID else "none",
    )

    # Jenkins returns 201 with a Location header pointing to the queue item
    queue_url = f"{request.base_url}queue/item/{queue_id}/"
    return Response(
        status_code=201,
        headers={"Location": queue_url},
    )


# ---------------------------------------------------------------------------
# Jenkins API: queue management
# ---------------------------------------------------------------------------


@router.post("/queue/cancelItem")
async def cancel_queue_item(manager: ManagerDep, id: int = Query()) -> Response:
    """Cancel a queued/running build."""
    import logging

    logger = logging.getLogger(__name__)

    build = manager.queue.get(id)
    if build is None:
        return Response(status_code=404)

    build.cancelled = True
    build.result = "ABORTED"
    build.building = False
    build.duration_ms = int((time.time() - build.timestamp) * 1000)

    if build.task and not build.task.done():
        build.task.cancel()

    logger.info("Build cancelled: queue_id=%d", id)
    return Response(status_code=204)


@router.get("/queue/item/{queue_id}/api/json", response_model=None)
async def queue_item_info(manager: ManagerDep, queue_id: int) -> dict[str, Any] | Response:
    """Return queue item info — includes executable.number if build started."""
    build = manager.queue.get(queue_id)
    if build is None:
        return Response(status_code=404)

    result: dict[str, Any] = {
        "id": queue_id,
        "blocked": False,
        "buildable": build.building,
    }

    if build.cancelled:
        result["cancelled"] = True
        result["buildable"] = False

    # Build has started (immediately in our mock)
    result["executable"] = {
        "number": build.build_number,
        "url": f"/job/mock/{build.build_number}/",
    }

    return result


# ---------------------------------------------------------------------------
# Jenkins API: stop running build
# ---------------------------------------------------------------------------


@router.post("/job/{job_name}/{build_number}/stop")
async def stop_build(manager: ManagerDep, job_name: str, build_number: int) -> Response:
    """Stop a running build."""
    import logging

    logger = logging.getLogger(__name__)

    build = manager.builds.get(build_number)
    if build is None:
        return Response(status_code=404)

    if build.building:
        build.cancelled = True
        build.result = "ABORTED"
        build.building = False
        build.duration_ms = int((time.time() - build.timestamp) * 1000)

        if build.task and not build.task.done():
            build.task.cancel()

        logger.info("Build stopped: #%d", build_number)

    return Response(status_code=302)


# ---------------------------------------------------------------------------
# Jenkins API: per-build status + artifact download
# ---------------------------------------------------------------------------


@router.get("/job/{job_name}/{build_number}/api/json", response_model=None)
async def build_api(
    manager: ManagerDep, job_name: str, build_number: int, tree: str = ""
) -> dict[str, Any] | Response:
    """Return individual build info — status, result, actions, artifacts."""
    build = manager.builds.get(build_number)
    if build is None:
        return Response(status_code=404)

    actions: list[dict[str, Any]] = [
        {
            "parameters": [
                {"name": "BRANCH", "value": build.branch},
                {"name": "BOT_REQUEST_ID", "value": build.request_id},
            ]
        },
    ]

    # Add lastBuiltRevision when build is complete (simulates Git plugin)
    if not build.building and build.commit_hash:
        actions.append({
            "lastBuiltRevision": {"SHA1": build.commit_hash},
        })

    result: dict[str, Any] = {
        "_class": "org.jenkinsci.plugins.workflow.job.WorkflowRun",
        "number": build.build_number,
        "result": build.result if not build.building else None,
        "building": build.building,
        "timestamp": int(build.timestamp * 1000),
        "duration": build.duration_ms,
        "actions": actions,
    }

    # Artifacts only present when build succeeded
    if build.result == "SUCCESS":
        result["artifacts"] = [
            {"relativePath": "build/app/outputs/flutter-apk/app-release.apk"}
        ]
    else:
        result["artifacts"] = []

    return result


@router.get("/job/{job_name}/{build_number}/artifact/{artifact_path:path}")
async def download_artifact(
    manager: ManagerDep,
    job_name: str,
    build_number: int,
    artifact_path: str,
) -> Response:
    """Serve a dummy APK artifact for download."""
    build = manager.builds.get(build_number)
    if build is None or build.result != "SUCCESS":
        return Response(status_code=404)

    return Response(
        content=DUMMY_APK,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="app-release.apk"'
        },
    )


# ---------------------------------------------------------------------------
# Jenkins API: CSRF crumb
# ---------------------------------------------------------------------------


@router.get("/crumbIssuer/api/json")
async def crumb_issuer() -> dict[str, str]:
    """Return a mock CSRF crumb — always accepted by the mock."""
    return {
        "crumb": "mock-crumb-token",
        "crumbRequestField": "Jenkins-Crumb",
    }
