"""Build coordinator — coordinates Jenkins, file-manager, and frontends.

The ``BuildCoordinator`` is the central coordinator for the build lifecycle.
It triggers builds on Jenkins, receives webhook callbacks when builds complete,
delegates artifact upload to the file-manager service, and forwards results
to registered frontend callback URLs.

Owns:
  - Per-build timeout tasks (no polling — each build carries its own deadline)
  - Build retention enforcement (evicts old builds, deletes Drive files)
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from .jenkins_client import JenkinsClient, JenkinsTriggerError
from .state import BuildTracker, CompletedBuild

logger = logging.getLogger(__name__)


class BuildCoordinator:
    """Coordinates the full build lifecycle.

    Owned by ``BuildManager`` and attached to ``app.state``.

    Flow:
        1. Frontend calls ``trigger_build(branch, callback_url)``
        2. Orchestrator triggers Jenkins and registers a ``PendingBuild``
        3. Per-build timeout task starts (``asyncio.sleep``)
        4. Jenkins agent runs the build, then POSTs to the webhook
        5. Orchestrator cancels the timeout task, uploads artifact via
           file-manager, enforces retention (deletes old Drive files)
        6. Orchestrator forwards the result to the frontend callback URL
    """

    def __init__(
        self,
        *,
        data_dir: Path,
        self_url: str,
        file_manager_url: str,
        max_recent_builds: int = 3,
        build_timeout: int = 30,
    ) -> None:
        self._data_dir = data_dir
        self._self_url = self_url.rstrip("/")
        self._file_manager_url = file_manager_url.rstrip("/")
        self._build_timeout = build_timeout
        self._tracker = BuildTracker(data_dir, max_recent_builds=max_recent_builds)
        self._jenkins: JenkinsClient | None = None
        self._http = httpx.AsyncClient(timeout=30.0)
        self._timeout_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def tracker(self) -> BuildTracker:
        return self._tracker

    @property
    def jenkins(self) -> JenkinsClient | None:
        return self._jenkins

    def init_jenkins(self, url: str, user: str, api_token: str, job_name: str) -> None:
        """Initialise (or re-initialise) the Jenkins client."""
        self._jenkins = JenkinsClient(url, user, api_token, job_name)
        logger.info("Jenkins client initialised for %s", url)

    @property
    def webhook_url(self) -> str:
        """The URL that Jenkins should call on build completion."""
        return f"{self._self_url}/api/builds/webhook"

    async def close(self) -> None:
        """Shut down HTTP clients and cancel pending timeout tasks."""
        # Cancel all outstanding timeout tasks
        for task in self._timeout_tasks.values():
            task.cancel()
        self._timeout_tasks.clear()

        if self._jenkins:
            await self._jenkins.close()
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Build trigger
    # ------------------------------------------------------------------

    async def trigger_build(
        self, branch: str, *, frontend_callback_url: str = ""
    ) -> dict[str, Any]:
        """Trigger a Jenkins build for the given branch.

        Returns ``{request_id, status}`` on success.

        Raises ``JenkinsTriggerError`` on failure.
        """
        if self._jenkins is None:
            raise JenkinsTriggerError(
                detail="Jenkins client not initialised",
                user_message="Build server not configured. Contact your admin.",
            )

        request_id = BuildTracker.generate_request_id()
        job_id = request_id  # job_id == request_id for simplicity

        queue_id = await self._jenkins.trigger_build(
            branch=branch,
            callback_url=self.webhook_url,
            request_id=request_id,
            job_id=job_id,
        )

        self._tracker.add_pending(
            request_id,
            branch,
            queue_id=queue_id,
            frontend_callback_url=frontend_callback_url,
        )

        # Start per-build timeout task
        self._start_timeout_task(request_id)

        logger.info(
            "Build triggered: request_id=%s branch=%s queue_id=%d",
            request_id,
            branch,
            queue_id,
        )
        return {"request_id": request_id, "status": "queued"}

    # ------------------------------------------------------------------
    # Timeout management
    # ------------------------------------------------------------------

    def _start_timeout_task(self, request_id: str) -> None:
        """Spawn an asyncio task that fires after build_timeout minutes."""
        timeout_seconds = self._build_timeout * 60
        if timeout_seconds <= 0:
            return
        task = asyncio.create_task(self._timeout_worker(request_id, timeout_seconds))
        self._timeout_tasks[request_id] = task

    def _cancel_timeout_task(self, request_id: str) -> None:
        """Cancel the timeout task for a build (webhook arrived in time)."""
        task = self._timeout_tasks.pop(request_id, None)
        if task is not None:
            task.cancel()

    async def _timeout_worker(self, request_id: str, timeout_seconds: float) -> None:
        """Sleep until the build deadline, then handle timeout."""
        try:
            await asyncio.sleep(timeout_seconds)
        except asyncio.CancelledError:
            return  # Webhook arrived — build completed normally

        # Timer fired — build timed out
        self._timeout_tasks.pop(request_id, None)
        await self._handle_timeout(request_id)

    async def _handle_timeout(self, request_id: str) -> None:
        """Handle a build that exceeded its timeout.

        Consumes the pending record, records a timeout completion,
        and notifies the frontend callback.
        """
        pending = self._tracker.consume_pending(request_id)
        if pending is None:
            return  # Already consumed by a webhook or cancellation

        now = time.time()
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
    # Webhook handler
    # ------------------------------------------------------------------

    async def handle_webhook(
        self,
        metadata: dict[str, Any],
        artifact_path: str | None,
    ) -> dict[str, str]:
        """Process a build-complete webhook from the Jenkins agent.

        1. Cancel the timeout task for this build
        2. Match to a pending build
        3. If success + artifact, upload via file-manager
        4. Record as completed, enforce retention
        5. Delete Drive files for evicted builds
        6. Forward result to the frontend callback URL

        Returns ``{status: "processed"|"ignored"}``.
        """
        request_id = metadata.get("request_id", "")

        # Cancel the timeout — webhook arrived in time
        self._cancel_timeout_task(request_id)

        pending = self._tracker.consume_pending(request_id)
        if pending is None:
            logger.warning("Webhook for unknown request_id: %s", request_id)
            return {"status": "ignored"}

        build_status = metadata.get("status", "")
        commit_hash = metadata.get("commit_hash", "")
        now = time.time()

        download_url = ""
        file_id = ""

        # Upload artifact on success
        if build_status == "success" and artifact_path:
            try:
                upload_result = await self._upload_artifact(artifact_path)
                download_url = upload_result.get("download_url", "")
                file_id = upload_result.get("file_id", "")
            except Exception:
                logger.exception("Artifact upload failed for %s", request_id)

        # Record in completed builds (enforces retention)
        completed, evicted = self._tracker.record_completed(
            request_id,
            branch=pending.branch,
            commit_hash=commit_hash,
            result=build_status,
            triggered_at=pending.triggered_at,
            completed_at=now,
            download_url=download_url,
            file_id=file_id,
        )

        # Delete Drive files for evicted builds (best-effort)
        await self._evict_builds(evicted)

        # Forward to frontend callback
        if pending.frontend_callback_url:
            await self._notify_frontend(pending.frontend_callback_url, completed)

        return {"status": "processed"}

    async def _upload_artifact(self, artifact_path: str) -> dict[str, Any]:
        """Upload a build artifact to the file-manager service."""
        url = f"{self._file_manager_url}/api/files/upload"
        path = Path(artifact_path)
        content = await asyncio.to_thread(path.read_bytes)
        resp = await self._http.post(
            url,
            files={"file": (path.name, content)},
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
        # Cancel the timeout task
        self._cancel_timeout_task(request_id)

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
