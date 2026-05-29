"""Build coordinator — coordinates Jenkins, file-manager, and frontends.

The ``BuildCoordinator`` is the central coordinator for the build lifecycle.
It triggers builds on Jenkins, then polls the Jenkins REST API for build
completion.  When a build finishes, it downloads archived artifacts, uploads
them to file-manager, and forwards results to registered frontend callback
URLs.

Completed build history is owned by file-manager — the coordinator sends
build metadata alongside artifacts via ``POST /api/files/builds/record``.
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

from config_core import get_service_auth_headers

from .jenkins_client import JenkinsBuild, JenkinsClient, JenkinsTriggerError
from .state import BuildTracker

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
        6. Sends artifact + metadata to file-manager via ``POST /api/files/builds/record``
        7. Forwards the result to the frontend callback URL
        8. If ``build_timeout`` minutes elapse without completion → timeout
    """

    def __init__(
        self,
        *,
        data_dir: Path,
        jenkins: JenkinsClient,
        file_manager_url: str,
        agent_control_url: str = "",
        build_timeout: int = 30,
        poll_interval: int = 10,
        artifact_pattern: str = "*.apk",
        estimated_duration_ms: int | None = None,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._data_dir = data_dir
        self._jenkins = jenkins
        self._file_manager_url = file_manager_url.rstrip("/")
        self._agent_control_url = agent_control_url.rstrip("/") if agent_control_url else ""
        self._build_timeout = build_timeout
        self._poll_interval = poll_interval
        self._artifact_pattern = artifact_pattern
        self._estimated_duration_ms = estimated_duration_ms
        self._clock = clock
        self._tracker = BuildTracker(
            data_dir, clock=clock,
        )
        self._http = http_client or httpx.AsyncClient(
            timeout=30.0, headers=get_service_auth_headers()
        )
        self._poll_tasks: dict[str, asyncio.Task[None]] = {}


    @property
    def tracker(self) -> BuildTracker:
        return self._tracker

    @property
    def jenkins(self) -> JenkinsClient:
        return self._jenkins

    async def close(self) -> None:
        """Shut down HTTP clients and cancel pending poll tasks."""
        # Force-disconnect VPN before tearing down HTTP clients. On shutdown
        # no poll tasks will run, so any remaining pending builds are
        # effectively abandoned — leaving VPN connected would be orphaned.
        await self._force_disconnect_vpn()

        for task in self._poll_tasks.values():
            task.cancel()
        self._poll_tasks.clear()

        if self._jenkins:
            await self._jenkins.close()
        await self._http.aclose()

    async def _connect_vpn(self) -> None:
        """Connect VPN prior to build (best-effort)."""
        if not self._agent_control_url:
            return
        try:
            logger.info("Initiating VPN connection on agent-control at %s...", self._agent_control_url)
            resp = await self._http.post(f"{self._agent_control_url}/control/vpn/connect")
            resp.raise_for_status()
            logger.info("VPN connection initiated successfully.")
        except Exception as e:
            logger.warning("Failed to initiate VPN connection: %s. Proceeding with build...", e)

    async def _disconnect_vpn_if_idle(self) -> None:
        """Disconnect VPN if no pending builds are left (best-effort)."""
        if not self._agent_control_url:
            return
        if self._tracker.pending_count == 0:
            try:
                logger.info("No pending builds left. Initiating VPN disconnection on agent-control...")
                resp = await self._http.post(f"{self._agent_control_url}/control/vpn/disconnect")
                resp.raise_for_status()
                logger.info("VPN disconnection initiated successfully.")
            except Exception as e:
                logger.warning("Failed to initiate VPN disconnection: %s", e)

    async def _force_disconnect_vpn(self) -> None:
        """Unconditionally disconnect VPN (best-effort).

        Used during shutdown when pending builds are abandoned and no poll
        tasks will run to eventually call ``_disconnect_vpn_if_idle``.
        """
        if not self._agent_control_url:
            return
        try:
            logger.info("Forcing VPN disconnection on shutdown...")
            resp = await self._http.post(f"{self._agent_control_url}/control/vpn/disconnect")
            resp.raise_for_status()
            logger.info("VPN disconnection initiated successfully.")
        except Exception as e:
            logger.warning("Failed to force VPN disconnection: %s", e)

    # ------------------------------------------------------------------
    # Build trigger
    # ------------------------------------------------------------------

    async def _estimate_duration(self, branch: str) -> int:
        """Estimate build duration in seconds for the given branch.

        Scans recent Jenkins build history for the most recent successful
        run of the same branch and uses its actual duration.  Falls back
        to the job-level ``estimatedDuration`` cached at startup.  Returns
        ``0`` when no estimate is available.
        """
        try:
            builds = await self._jenkins.get_builds(count=20)
            for build in builds:
                if (
                    build.branch == branch
                    and build.result == "SUCCESS"
                    and build.duration_ms > 0
                ):
                    return build.duration_ms // 1000
        except Exception:
            logger.debug("Could not fetch build history for estimation")

        if self._estimated_duration_ms and self._estimated_duration_ms > 0:
            return self._estimated_duration_ms // 1000
        return 0

    async def trigger_build(
        self, branch: str, *, frontend_callback_url: str = "", app_name: str | None = None
    ) -> dict[str, Any]:
        """Trigger a Jenkins build for the given branch.

        Returns ``{request_id, status, estimated_duration}`` on success.

        Raises ``JenkinsTriggerError`` on failure.
        """
        request_id = BuildTracker.generate_request_id()

        # Resolve branch-specific estimated duration before triggering
        estimated_duration = await self._estimate_duration(branch)

        # Initiate VPN connection before triggering Jenkins build
        await self._connect_vpn()

        try:
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
        except Exception:
            # If Jenkins trigger or state persistence fails after VPN was
            # connected, disconnect to avoid orphaned VPN sessions.
            await self._disconnect_vpn_if_idle()
            raise

        # Start per-build poll task
        self._start_poll_task(request_id)

        logger.info(
            "Build triggered: request_id=%s branch=%s queue_id=%d",
            request_id,
            branch,
            queue_id,
        )
        return {
            "request_id": request_id,
            "status": "queued",
            "estimated_duration": estimated_duration,
        }

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
        except Exception:
            # Unexpected crash — consume the pending build to unblock VPN
            # disconnect, otherwise pending_count stays > 0 forever.
            logger.exception(
                "Poll worker crashed for %s — consuming pending build",
                request_id,
            )
            self._poll_tasks.pop(request_id, None)
            self._tracker.consume_pending(request_id)
            await self._disconnect_vpn_if_idle()

    # ------------------------------------------------------------------
    # Build completion
    # ------------------------------------------------------------------

    async def _complete_build(
        self, request_id: str, jenkins_build: JenkinsBuild
    ) -> None:
        """Process a completed Jenkins build.

        Downloads the artifact (if success), sends it with metadata to
        file-manager, and notifies the frontend.
        """
        pending = self._tracker.consume_pending(request_id)
        if pending is None:
            return  # Already consumed by cancellation

        now = self._clock()
        artifact_data: tuple[str, bytes] | None = None

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
                    # {baseName}-{YYYYMMDD}-{HHmmss}-{requestId8}.apk
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
                    artifact_data = (upload_name, content)
            except Exception:
                logger.exception(
                    "Artifact download failed for %s", request_id
                )

        # Capture artifact size before uploading
        artifact_size = len(artifact_data[1]) if artifact_data else 0

        # Record build in file-manager (with or without artifact)
        record_result = await self._record_build(
            request_id=request_id,
            branch=pending.branch,
            commit_hash=jenkins_build.commit_hash,
            result=build_status,
            triggered_at=pending.triggered_at,
            completed_at=now,
            artifact=artifact_data,
            file_size=artifact_size,
            build_number=jenkins_build.number,
        )

        if pending.frontend_callback_url:
            await self._notify_frontend(
                pending.frontend_callback_url,
                request_id=request_id,
                branch=pending.branch,
                commit_hash=jenkins_build.commit_hash,
                result=build_status,
                triggered_at=pending.triggered_at,
                completed_at=now,
                download_url=record_result.get("download_url", ""),
                build_number=jenkins_build.number,
            )

        await self._disconnect_vpn_if_idle()

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

        Consumes the pending record, records a timeout in file-manager,
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

        # Record timeout in file-manager (no artifact)
        await self._record_build(
            request_id=request_id,
            branch=pending.branch,
            commit_hash="",
            result="timeout",
            triggered_at=pending.triggered_at,
            completed_at=now,
        )

        # Notify frontend
        if pending.frontend_callback_url:
            await self._notify_frontend(
                pending.frontend_callback_url,
                request_id=request_id,
                branch=pending.branch,
                commit_hash="",
                result="timeout",
                triggered_at=pending.triggered_at,
                completed_at=now,
                download_url="",
            )

        await self._disconnect_vpn_if_idle()

    # ------------------------------------------------------------------
    # Artifact upload
    # ------------------------------------------------------------------

    async def _record_build(
        self,
        *,
        request_id: str,
        branch: str,
        commit_hash: str,
        result: str,
        triggered_at: float,
        completed_at: float,
        artifact: tuple[str, bytes] | None = None,
        file_size: int = 0,
        build_number: int = 0,
    ) -> dict[str, Any]:
        """Send build metadata (and optional artifact) to file-manager.

        Calls ``POST /api/files/builds/record`` with multipart form data.
        Returns the response JSON (contains ``file_id`` and ``download_url``
        when an artifact was uploaded).
        """
        url = f"{self._file_manager_url}/api/files/builds/record"
        form_data = {
            "request_id": request_id,
            "branch": branch,
            "commit_hash": commit_hash,
            "result": result,
            "triggered_at": str(triggered_at),
            "completed_at": str(completed_at),
            "file_size": str(file_size),
            "build_number": str(build_number),
        }

        files = None
        if artifact is not None:
            filename, content = artifact
            files = {"file": (filename, content)}

        try:
            resp = await self._http.post(url, data=form_data, files=files)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception(
                "Failed to record build %s in file-manager", request_id
            )
            return {}

    async def _notify_frontend(
        self,
        callback_url: str,
        *,
        request_id: str,
        branch: str,
        commit_hash: str,
        result: str,
        triggered_at: float,
        completed_at: float,
        download_url: str = "",
        build_number: int = 0,
    ) -> None:
        """Forward a build result to the frontend's callback URL.

        Best-effort — errors are logged but never propagated.
        """
        payload = {
            "request_id": request_id,
            "branch": branch,
            "commit_hash": commit_hash,
            "result": result,
            "triggered_at": triggered_at,
            "completed_at": completed_at,
            "download_url": download_url,
            "build_number": build_number,
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
        await self._disconnect_vpn_if_idle()
        return {"status": "cancelled"}
