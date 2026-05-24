"""Build coordinator — coordinates Jenkins, file-manager, and frontends.

The ``BuildCoordinator`` is the central coordinator for the build lifecycle.
It triggers builds on Jenkins, then polls the Jenkins REST API for build
completion.  When a build finishes, it downloads archived artifacts, uploads
them to file-manager, and forwards results to registered frontend callback
URLs.

Owns:
  - Per-build poll tasks (periodically checks Jenkins until done or timeout)
  - Build retention enforcement (evicts old builds, deletes Drive files)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .jenkins_client import JenkinsBuild, JenkinsClient, JenkinsTriggerError
from .state import BuildTracker, CompletedBuild

logger = logging.getLogger(__name__)


class BuildCoordinator:
    """Coordinates the full build lifecycle.

    Owned by ``BuildManager`` and attached to ``app.state``.

    Flow:
        1. Frontend calls ``trigger_build(branch, callback_url)``
        2. Coordinator triggers Jenkins and registers a ``PendingBuild``
        3. A per-build poll task starts (periodic ``asyncio.sleep``)
        4. Poll task queries Jenkins REST API every ``poll_interval`` seconds
        5. When build finishes → downloads artifact from Jenkins archive
        6. Uploads to file-manager, enforces retention
        7. Forwards the result to the frontend callback URL
        8. If ``build_timeout`` minutes elapse without completion → timeout
    """

    def __init__(
        self,
        *,
        data_dir: Path,
        jenkins: JenkinsClient,
        file_manager_url: str,
        max_recent_builds: int = 3,
        build_timeout: int = 30,
        poll_interval: int = 10,
        artifact_pattern: str = "*.apk",
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._data_dir = data_dir
        self._jenkins = jenkins
        self._file_manager_url = file_manager_url.rstrip("/")
        self._build_timeout = build_timeout
        self._poll_interval = poll_interval
        self._artifact_pattern = artifact_pattern
        self._clock = clock
        self._tracker = BuildTracker(
            data_dir, max_recent_builds=max_recent_builds, clock=clock,
        )
        self._http = http_client or httpx.AsyncClient(timeout=30.0)
        self._poll_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def tracker(self) -> BuildTracker:
        return self._tracker

    @property
    def jenkins(self) -> JenkinsClient:
        return self._jenkins

    async def close(self) -> None:
        """Shut down HTTP clients and cancel pending poll tasks."""
        for task in self._poll_tasks.values():
            task.cancel()
        self._poll_tasks.clear()

        if self._jenkins:
            await self._jenkins.close()
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Build trigger
    # ------------------------------------------------------------------

    async def trigger_build(
        self, branch: str, *, frontend_callback_url: str = "", app_name: str | None = None
    ) -> dict[str, Any]:
        """Trigger a Jenkins build for the given branch.

        Returns ``{request_id, status}`` on success.

        Raises ``JenkinsTriggerError`` on failure.
        """
        if self._tracker.is_queue_full:
            raise JenkinsTriggerError(
                detail="Queue full: pending builds == max_recent_builds",
                user_message=(
                    "The build queue is full. Please wait for an existing build "
                    "to finish or cancel one before starting a new build."
                ),
            )

        request_id = BuildTracker.generate_request_id()

        queue_id = await self._jenkins.trigger_build(
            branch=branch,
            request_id=request_id,
        )

        self._tracker.add_pending(
            request_id,
            branch,
            queue_id=queue_id,
            frontend_callback_url=frontend_callback_url,
            app_name=app_name,
        )

        # Start per-build poll task
        self._start_poll_task(request_id)

        logger.info(
            "Build triggered: request_id=%s branch=%s queue_id=%d",
            request_id,
            branch,
            queue_id,
        )
        return {"request_id": request_id, "status": "queued"}

    # ------------------------------------------------------------------
    # Poll-based completion detection
    # ------------------------------------------------------------------

    def _start_poll_task(self, request_id: str) -> None:
        """Spawn an asyncio task that polls Jenkins until the build completes."""
        task = asyncio.create_task(
            self._poll_worker(request_id)
        )
        self._poll_tasks[request_id] = task

    def _cancel_poll_task(self, request_id: str) -> None:
        """Cancel the poll task for a build (e.g. on manual cancellation)."""
        task = self._poll_tasks.pop(request_id, None)
        if task is not None:
            task.cancel()

    async def _poll_worker(self, request_id: str) -> None:
        """Periodically query Jenkins until the build finishes or times out.

        This is the heart of the polling approach.  Each pending build gets
        its own poll worker.  The worker:

        1. Sleeps for ``poll_interval`` seconds
        2. Queries Jenkins for builds matching ``request_id``
        3. If found and ``building == False`` → calls ``_complete_build()``
        4. If total elapsed time exceeds ``build_timeout`` → times out
        5. If Jenkins is unreachable → logs warning and retries next interval
        """
        timeout_seconds = self._build_timeout * 60
        start_time = self._clock()

        try:
            while True:
                await asyncio.sleep(self._poll_interval)

                elapsed = self._clock() - start_time

                # Check timeout
                if timeout_seconds > 0 and elapsed >= timeout_seconds:
                    self._poll_tasks.pop(request_id, None)
                    await self._handle_timeout(request_id)
                    return

                try:
                    builds = await self._jenkins.get_builds(count=10)
                except Exception:
                    logger.warning(
                        "Failed to poll Jenkins for %s — will retry",
                        request_id,
                    )
                    continue

                # Look for our build
                for build in builds:
                    if build.request_id == request_id and not build.building:
                        self._poll_tasks.pop(request_id, None)
                        await self._complete_build(request_id, build)
                        return

        except asyncio.CancelledError:
            return  # Build was cancelled manually

    # ------------------------------------------------------------------
    # Build completion
    # ------------------------------------------------------------------

    async def _complete_build(
        self, request_id: str, jenkins_build: JenkinsBuild
    ) -> None:
        """Process a completed Jenkins build.

        Downloads the artifact (if success), uploads to file-manager,
        records the completion, enforces retention, and notifies the frontend.
        """
        pending = self._tracker.consume_pending(request_id)
        if pending is None:
            return  # Already consumed by cancellation

        now = self._clock()
        download_url = ""
        file_id = ""

        # Jenkins uses uppercase (SUCCESS/FAILURE/ABORTED), we use lowercase
        if jenkins_build.result == "SUCCESS":
            build_status = "success"
        elif jenkins_build.result == "ABORTED":
            build_status = "cancelled"
        else:
            build_status = "failure"

        if build_status == "success" and jenkins_build.number:
            try:
                artifact = await self._jenkins.download_artifact(
                    jenkins_build.number, self._artifact_pattern
                )
                if artifact:
                    original_name, content = artifact
                    # Build a descriptive filename:
                    # {jobName}-{YYYYMMDD}-{HHmmss}-{requestId8}.apk
                    # If app_name is provided, use a sanitized version of it.
                    suffix = Path(original_name).suffix  # .apk
                    dt = datetime.fromtimestamp(now, tz=timezone.utc)
                    if pending.app_name:
                        import re
                        cleaned = pending.app_name.replace(" ", "-")
                        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", cleaned).lower()
                        base_name = cleaned or self._jenkins.job_name
                    else:
                        base_name = self._jenkins.job_name

                    upload_name = (
                        f"{base_name}"
                        f"-{dt.strftime('%Y%m%d')}"
                        f"-{dt.strftime('%H%M%S')}"
                        f"-{request_id[:8]}{suffix}"
                    )
                    upload_result = await self._upload_artifact(
                        upload_name, content
                    )
                    download_url = upload_result.get("download_url", "")
                    file_id = upload_result.get("file_id", "")
            except Exception:
                logger.exception(
                    "Artifact download/upload failed for %s", request_id
                )

        completed, evicted = self._tracker.record_completed(
            request_id,
            branch=pending.branch,
            commit_hash=jenkins_build.commit_hash,
            result=build_status,
            triggered_at=pending.triggered_at,
            completed_at=now,
            download_url=download_url,
            file_id=file_id,
        )

        await self._evict_builds(evicted)

        if pending.frontend_callback_url:
            await self._notify_frontend(pending.frontend_callback_url, completed)

        logger.info(
            "Build completed: request_id=%s result=%s",
            request_id,
            build_status,
        )

    # ------------------------------------------------------------------
    # Timeout handler
    # ------------------------------------------------------------------

    async def _handle_timeout(self, request_id: str) -> None:
        """Handle a build that exceeded its timeout.

        Consumes the pending record, records a timeout completion,
        and notifies the frontend callback.
        """
        pending = self._tracker.consume_pending(request_id)
        if pending is None:
            return  # Already consumed by a webhook or cancellation

        now = self._clock()
        logger.warning(
            "Build timed out: request_id=%s branch=%s (%.0fs elapsed)",
            request_id,
            pending.branch,
            now - pending.triggered_at,
        )

        completed, evicted = self._tracker.record_completed(
            request_id,
            branch=pending.branch,
            commit_hash="",
            result="timeout",
            triggered_at=pending.triggered_at,
            completed_at=now,
        )

        # Evict old builds (best-effort)
        await self._evict_builds(evicted)

        # Notify frontend
        if pending.frontend_callback_url:
            await self._notify_frontend(pending.frontend_callback_url, completed)

    # ------------------------------------------------------------------
    # Artifact upload
    # ------------------------------------------------------------------

    async def _upload_artifact(
        self, filename: str, content: bytes
    ) -> dict[str, Any]:
        """Upload a build artifact to the file-manager service."""
        url = f"{self._file_manager_url}/api/files/upload"
        resp = await self._http.post(
            url,
            files={"file": (filename, content)},
        )
        resp.raise_for_status()
        return resp.json()

    async def _evict_builds(self, evicted: list[CompletedBuild]) -> None:
        """Delete Drive files for evicted builds.

        Best-effort — failures are logged but never propagated.
        """
        for build in evicted:
            if not build.file_id:
                continue
            try:
                url = f"{self._file_manager_url}/api/files/{build.file_id}"
                resp = await self._http.delete(url)
                if resp.status_code < 400:
                    logger.info(
                        "Evicted build %s — deleted Drive file %s",
                        build.request_id,
                        build.file_id,
                    )
                else:
                    logger.error(
                        "Failed to delete Drive file %s for evicted build %s: %d",
                        build.file_id,
                        build.request_id,
                        resp.status_code,
                    )
            except Exception:
                logger.exception(
                    "Failed to delete Drive file %s for evicted build %s",
                    build.file_id,
                    build.request_id,
                )

    async def _notify_frontend(
        self,
        callback_url: str,
        completed: CompletedBuild,
    ) -> None:
        """Forward a build result to the frontend's callback URL.

        Best-effort — errors are logged but never propagated.
        """
        payload = {
            "request_id": completed.request_id,
            "branch": completed.branch,
            "commit_hash": completed.commit_hash,
            "result": completed.result,
            "triggered_at": completed.triggered_at,
            "completed_at": completed.completed_at,
            "download_url": completed.download_url,
        }
        try:
            resp = await self._http.post(callback_url, json=payload)
            if resp.status_code >= 400:
                logger.error(
                    "Frontend callback failed: %s → %d",
                    callback_url,
                    resp.status_code,
                )
        except Exception:
            logger.exception("Failed to notify frontend: %s", callback_url)

    # ------------------------------------------------------------------
    # Build cancellation
    # ------------------------------------------------------------------

    async def cancel_build(self, request_id: str) -> dict[str, str]:
        """Cancel a pending build — stop Jenkins and remove from tracking."""
        # Cancel the poll task
        self._cancel_poll_task(request_id)

        pending = self._tracker.get_pending(request_id)
        if pending is None:
            return {"status": "not_found"}

        if pending.queue_id is not None and self._jenkins:
            try:
                await self._jenkins.cancel_build(pending.queue_id)
            except Exception:
                logger.exception(
                    "Failed to cancel Jenkins build (queue_id=%d)",
                    pending.queue_id,
                )

        self._tracker.consume_pending(request_id)
        return {"status": "cancelled"}
