"""Mock build manager — owns in-memory state and build simulation logic."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import MockJenkinsConfig

logger = logging.getLogger(__name__)

# A tiny byte sequence that starts with the ZIP magic number (PK\x03\x04)
# followed by "mock-apk" marker.  Not a valid APK but enough for the bot's
# webhook handler which just saves and forwards the file.
DUMMY_APK = b"PK\x03\x04" + b"mock-jenkins-dummy-apk-artifact" + b"\x00" * 64


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


class MockBuildManager:
    """Manages mock build state and background simulation tasks.

    All mutable state lives here (not at module level) so that
    ``create_app()`` produces fully independent app instances.
    """

    def __init__(self, config: MockJenkinsConfig) -> None:
        self.config = config
        self._next_queue_id = 1
        self._next_build_number = 1
        # queue_id → MockBuild
        self.queue: dict[int, MockBuild] = {}
        # build_number → MockBuild (same objects as queue, indexed differently)
        self.builds: dict[int, MockBuild] = {}
        # All builds for history (newest last)
        self.build_history: list[MockBuild] = []

    def allocate_ids(self) -> tuple[int, int]:
        """Allocate the next queue ID and build number."""
        qid = self._next_queue_id
        bnum = self._next_build_number
        self._next_queue_id += 1
        self._next_build_number += 1
        return qid, bnum

    def register_build(self, build: MockBuild) -> None:
        """Register a build in all indexes and start its simulation task."""
        self.queue[build.queue_id] = build
        self.builds[build.build_number] = build
        self.build_history.append(build)
        build.task = asyncio.create_task(self._simulate_build(build))

    async def _simulate_build(self, build: MockBuild) -> None:
        """Simulate a build by waiting, then posting the webhook callback."""
        try:
            await asyncio.sleep(self.config.mock_build_delay)

            if build.cancelled:
                logger.info("Build #%d was cancelled during simulation", build.build_number)
                return

            # Determine success/failure
            if self.config.mock_failure_rate > 0 and random.random() < self.config.mock_failure_rate:
                build.result = "FAILURE"
                build.building = False
                build.duration_ms = int((time.time() - build.timestamp) * 1000)
                logger.info("Build #%d simulated FAILURE", build.build_number)
                await self._send_callback(build, success=False)
            else:
                build.result = "SUCCESS"
                build.building = False
                build.duration_ms = int((time.time() - build.timestamp) * 1000)
                logger.info("Build #%d simulated SUCCESS", build.build_number)
                await self._send_callback(build, success=True)

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

    async def _send_callback(self, build: MockBuild, *, success: bool) -> None:
        """POST the webhook callback to the bot, mimicking the Jenkinsfile."""
        if not build.callback_url:
            logger.info("No callback URL for build #%d, skipping", build.build_number)
            return

        commit_hash = uuid.uuid4().hex[:40]  # Simulate a 40-char git hash

        metadata: dict[str, Any] = {
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
