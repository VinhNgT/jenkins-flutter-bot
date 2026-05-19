"""Mock build manager — owns in-memory state and build simulation logic.

The mock-jenkins is fully passive: it simulates build execution by sleeping
for a configurable delay, then marks the build as complete.  It never makes
outbound HTTP requests — build-manager discovers completion by polling the
mock's Jenkins REST API.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from dataclasses import dataclass, field

from .config import MockJenkinsConfig

logger = logging.getLogger(__name__)

# A tiny byte sequence that starts with the ZIP magic number (PK\x03\x04)
# followed by "mock-apk" marker.  Not a valid APK but enough for the
# build-manager's download_artifact handler which just saves and forwards.
DUMMY_APK = b"PK\x03\x04" + b"mock-jenkins-dummy-apk-artifact" + b"\x00" * 64


@dataclass
class MockBuild:
    """Tracks a single mock build."""

    queue_id: int
    build_number: int
    branch: str
    request_id: str
    building: bool = True
    result: str = ""  # "", "SUCCESS", "FAILURE", "ABORTED"
    timestamp: float = field(default_factory=time.time)
    duration_ms: int = 0
    cancelled: bool = False
    commit_hash: str = field(default_factory=lambda: uuid.uuid4().hex[:40])
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
        """Simulate a build by waiting, then marking it as complete.

        The mock-jenkins is fully passive — it never sends any outbound
        HTTP requests.  Build-manager discovers completion by polling.
        """
        try:
            await asyncio.sleep(self.config.mock_build_delay)

            if build.cancelled:
                logger.info("Build #%d was cancelled during simulation", build.build_number)
                return

            # Determine success/failure
            if self.config.mock_failure_rate > 0 and random.random() < self.config.mock_failure_rate:
                build.result = "FAILURE"
            else:
                build.result = "SUCCESS"

            build.building = False
            build.duration_ms = int((time.time() - build.timestamp) * 1000)
            logger.info("Build #%d completed: %s", build.build_number, build.result)

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
