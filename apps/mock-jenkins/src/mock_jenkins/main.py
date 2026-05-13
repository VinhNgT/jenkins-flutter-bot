"""Mock Jenkins server — simulates the Jenkins REST API for local development.

Implements only the endpoints that JenkinsClient actually uses:
  - GET  /job/{name}/api/json     — connection check + build history
  - POST /job/{name}/buildWithParameters — trigger a build
  - POST /queue/cancelItem        — cancel a queued build
  - GET  /queue/item/{id}/api/json — queue item info
  - POST /job/{name}/{number}/stop — stop a running build

On trigger, spawns a background task that waits MOCK_BUILD_DELAY seconds,
then POSTs a webhook callback to BOT_CALLBACK_URL with a dummy APK.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Query, Request, Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

MOCK_BUILD_DELAY = int(os.environ.get("MOCK_BUILD_DELAY", "10"))
MOCK_FAILURE_RATE = float(os.environ.get("MOCK_FAILURE_RATE", "0"))
MOCK_PORT = int(os.environ.get("MOCK_PORT", "8080"))

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

_next_queue_id = 1
_next_build_number = 1


@dataclass
class MockBuild:
    """Tracks a single mock build."""

    queue_id: int
    build_number: int
    branch: str
    callback_url: str
    request_id: str
    job_id: str
    building: bool = True
    result: str = ""  # "", "SUCCESS", "FAILURE", "ABORTED"
    timestamp: float = field(default_factory=time.time)
    duration_ms: int = 0
    cancelled: bool = False
    task: asyncio.Task[None] | None = field(default=None, repr=False)


# queue_id → MockBuild
_queue: dict[int, MockBuild] = {}

# build_number → MockBuild (same objects as _queue, indexed differently)
_builds: dict[int, MockBuild] = {}

# All builds for history (newest last)
_build_history: list[MockBuild] = []


def _allocate_ids() -> tuple[int, int]:
    """Allocate the next queue ID and build number."""
    global _next_queue_id, _next_build_number
    qid = _next_queue_id
    bnum = _next_build_number
    _next_queue_id += 1
    _next_build_number += 1
    return qid, bnum


# ---------------------------------------------------------------------------
# Dummy APK (minimal valid-looking bytes)
# ---------------------------------------------------------------------------

# A tiny byte sequence that starts with the ZIP magic number (PK\x03\x04)
# followed by "mock-apk" marker.  Not a valid APK but enough for the bot's
# webhook handler which just saves and forwards the file.
DUMMY_APK = b"PK\x03\x04" + b"mock-jenkins-dummy-apk-artifact" + b"\x00" * 64


# ---------------------------------------------------------------------------
# Background build simulation
# ---------------------------------------------------------------------------


async def _simulate_build(build: MockBuild) -> None:
    """Simulate a build by waiting, then posting the webhook callback."""
    try:
        # Wait for the configured build delay
        await asyncio.sleep(MOCK_BUILD_DELAY)

        if build.cancelled:
            logger.info("Build #%d was cancelled during simulation", build.build_number)
            return

        # Determine success/failure
        if MOCK_FAILURE_RATE > 0 and random.random() < MOCK_FAILURE_RATE:
            build.result = "FAILURE"
            build.building = False
            build.duration_ms = int((time.time() - build.timestamp) * 1000)
            logger.info("Build #%d simulated FAILURE", build.build_number)

            # Send failure callback
            await _send_callback(build, success=False)
        else:
            build.result = "SUCCESS"
            build.building = False
            build.duration_ms = int((time.time() - build.timestamp) * 1000)
            logger.info("Build #%d simulated SUCCESS", build.build_number)

            # Send success callback with dummy APK
            await _send_callback(build, success=True)

    except asyncio.CancelledError:
        build.result = "ABORTED"
        build.building = False
        build.duration_ms = int((time.time() - build.timestamp) * 1000)
        logger.info("Build #%d cancelled", build.build_number)
    except Exception:
        logger.exception("Error simulating build #%d", build.build_number)
        build.result = "FAILURE"
        build.building = False
        build.duration_ms = int((time.time() - build.timestamp) * 1000)


async def _send_callback(build: MockBuild, *, success: bool) -> None:
    """POST the webhook callback to the bot, mimicking the Jenkinsfile."""
    if not build.callback_url:
        logger.info("No callback URL for build #%d, skipping", build.build_number)
        return

    commit_hash = uuid.uuid4().hex[:40]  # Simulate a 40-char git hash

    metadata = {
        "request_id": build.request_id,
        "job_id": build.job_id,
        "status": "success" if success else "failure",
        "commit_hash": commit_hash,
    }

    if not success:
        metadata["logs"] = (
            "FAILURE: Simulated build failure from mock-jenkins.\n"
            "This is a test failure — no real compilation was attempted."
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if success:
                # Multipart POST with artifact
                files = {
                    "metadata": (None, json.dumps(metadata), "application/json"),
                    "artifact": (
                        "app-release.apk",
                        io.BytesIO(DUMMY_APK),
                        "application/octet-stream",
                    ),
                }
                resp = await client.post(build.callback_url, files=files)  # type: ignore
            else:
                # Multipart POST without artifact
                files = {
                    "metadata": (None, json.dumps(metadata), "application/json"),
                }
                resp = await client.post(build.callback_url, files=files)  # type: ignore

            logger.info(
                "Webhook callback sent to %s — status %d",
                build.callback_url,
                resp.status_code,
            )
    except Exception:
        logger.exception("Failed to send webhook callback to %s", build.callback_url)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="mock-jenkins")


@app.get("/")
async def root() -> dict[str, str]:
    """Health check."""
    return {"status": "mock-jenkins running", "build_delay": f"{MOCK_BUILD_DELAY}s"}


# ---------------------------------------------------------------------------
# Jenkins API: job info + build history
# ---------------------------------------------------------------------------


@app.get("/job/{job_name}/api/json")
async def job_api(job_name: str, tree: str = "") -> dict[str, Any]:
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
    for b in reversed(_build_history[-20:]):
        builds_json.append(
            {
                "number": b.build_number,
                "result": b.result if not b.building else None,
                "building": b.building,
                "timestamp": int(b.timestamp * 1000),  # s → ms
                "duration": b.duration_ms,
                "actions": [
                    {
                        "parameters": [
                            {"name": "BRANCH", "value": b.branch},
                            {"name": "BOT_CALLBACK_URL", "value": b.callback_url},
                            {"name": "BOT_REQUEST_ID", "value": b.request_id},
                            {"name": "BOT_JOB_ID", "value": b.job_id},
                        ]
                    }
                ],
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


@app.post("/job/{job_name}/buildWithParameters")
async def trigger_build(
    job_name: str,
    request: Request,
    BRANCH: str = Query(default="main"),
    BOT_CALLBACK_URL: str = Query(default=""),
    BOT_REQUEST_ID: str = Query(default=""),
    BOT_JOB_ID: str = Query(default=""),
) -> Response:
    """Accept a parameterised build trigger — mimics Jenkins 201 response."""
    queue_id, build_number = _allocate_ids()

    build = MockBuild(
        queue_id=queue_id,
        build_number=build_number,
        branch=BRANCH,
        callback_url=BOT_CALLBACK_URL,
        request_id=BOT_REQUEST_ID,
        job_id=BOT_JOB_ID,
    )

    _queue[queue_id] = build
    _builds[build_number] = build
    _build_history.append(build)

    # Start background build simulation
    build.task = asyncio.create_task(_simulate_build(build))

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


@app.post("/queue/cancelItem")
async def cancel_queue_item(id: int = Query()) -> Response:
    """Cancel a queued/running build."""
    build = _queue.get(id)
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


@app.get("/queue/item/{queue_id}/api/json", response_model=None)
async def queue_item_info(queue_id: int) -> dict[str, Any] | Response:
    """Return queue item info — includes executable.number if build started."""
    build = _queue.get(queue_id)
    if build is None:
        return Response(status_code=404)

    result: dict[str, Any] = {
        "id": queue_id,
        "blocked": False,
        "buildable": build.building,
    }

    # Build has started (immediately in our mock)
    result["executable"] = {
        "number": build.build_number,
        "url": f"/job/mock/{build.build_number}/",
    }

    return result


# ---------------------------------------------------------------------------
# Jenkins API: stop running build
# ---------------------------------------------------------------------------


@app.post("/job/{job_name}/{build_number}/stop")
async def stop_build(job_name: str, build_number: int) -> Response:
    """Stop a running build."""
    build = _builds.get(build_number)
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
# CLI entry point
# ---------------------------------------------------------------------------


def cli() -> None:
    """CLI entry point for the mock Jenkins server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    logger.info(
        "Starting mock-jenkins on port %d (delay=%ds, failure_rate=%.0f%%)",
        MOCK_PORT,
        MOCK_BUILD_DELAY,
        MOCK_FAILURE_RATE * 100,
    )
    uvicorn.run(app, host="0.0.0.0", port=MOCK_PORT)
