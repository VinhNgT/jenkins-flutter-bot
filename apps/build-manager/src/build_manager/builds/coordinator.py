"""Build coordinator — coordinates Jenkins, file-manager, and frontends.

The ``BuildCoordinator`` is the central coordinator for the build lifecycle.
It triggers builds on Jenkins, receives webhook callbacks when builds complete,
delegates artifact upload to the file-manager service, and forwards results
to registered frontend callback URLs.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx

from .jenkins_client import JenkinsClient, JenkinsTriggerError
from .state import BuildTracker

logger = logging.getLogger(__name__)


class BuildCoordinator:
    """Coordinates the full build lifecycle.

    Owned by ``BuildManager`` and attached to ``app.state``.

    Flow:
        1. Frontend calls ``trigger_build(branch, callback_url)``
        2. Orchestrator triggers Jenkins and registers a ``PendingBuild``
        3. Jenkins agent runs the build, then POSTs to the webhook
        4. Orchestrator receives webhook, uploads artifact via file-manager
        5. Orchestrator forwards the result to the frontend callback URL
    """

    def __init__(
        self,
        *,
        data_dir: Path,
        self_url: str,
        file_manager_url: str,
    ) -> None:
        self._data_dir = data_dir
        self._self_url = self_url.rstrip("/")
        self._file_manager_url = file_manager_url.rstrip("/")
        self._tracker = BuildTracker(data_dir)
        self._jenkins: JenkinsClient | None = None
        self._http = httpx.AsyncClient(timeout=30.0)

    @property
    def tracker(self) -> BuildTracker:
        return self._tracker

    @property
    def jenkins(self) -> JenkinsClient | None:
        return self._jenkins

    def init_jenkins(
        self, url: str, user: str, api_token: str, job_name: str
    ) -> None:
        """Initialise (or re-initialise) the Jenkins client."""
        self._jenkins = JenkinsClient(url, user, api_token, job_name)
        logger.info("Jenkins client initialised for %s", url)

    @property
    def webhook_url(self) -> str:
        """The URL that Jenkins should call on build completion."""
        return f"{self._self_url}/api/builds/webhook"

    async def close(self) -> None:
        """Shut down HTTP clients."""
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

        logger.info(
            "Build triggered: request_id=%s branch=%s queue_id=%d",
            request_id,
            branch,
            queue_id,
        )
        return {"request_id": request_id, "status": "queued"}

    # ------------------------------------------------------------------
    # Webhook handler
    # ------------------------------------------------------------------

    async def handle_webhook(
        self,
        metadata: dict[str, Any],
        artifact_path: str | None,
    ) -> dict[str, str]:
        """Process a build-complete webhook from the Jenkins agent.

        1. Match to a pending build
        2. If success + artifact, upload via file-manager
        3. Record as completed
        4. Forward result to the frontend callback URL

        Returns ``{status: "processed"|"ignored"}``.
        """
        request_id = metadata.get("request_id", "")
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

        # Record in completed builds
        completed = self._tracker.record_completed(
            request_id,
            branch=pending.branch,
            commit_hash=commit_hash,
            result=build_status,
            triggered_at=pending.triggered_at,
            completed_at=now,
            download_url=download_url,
            file_id=file_id,
        )

        # Forward to frontend callback
        if pending.frontend_callback_url:
            await self._notify_frontend(pending.frontend_callback_url, completed)

        return {"status": "processed"}

    async def _upload_artifact(self, artifact_path: str) -> dict[str, Any]:
        """Upload a build artifact to the file-manager service."""
        url = f"{self._file_manager_url}/api/files/upload"
        with open(artifact_path, "rb") as f:
            resp = await self._http.post(
                url,
                files={"file": (Path(artifact_path).name, f)},
            )
        resp.raise_for_status()
        return resp.json()

    async def _notify_frontend(
        self,
        callback_url: str,
        completed: Any,
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
