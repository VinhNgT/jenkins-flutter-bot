"""Jenkins REST API client for triggering and querying builds.

Provides methods for:
  - Triggering parameterised builds
  - Querying build history and results
  - Downloading archived artifacts
  - Cancelling queued or running builds
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class JenkinsTriggerError(Exception):
    """Raised when a Jenkins build trigger fails.

    Carries both a technical ``detail`` for logs and a jargon-free
    ``user_message`` suitable for display in frontend notifications.
    """

    def __init__(self, detail: str, user_message: str) -> None:
        super().__init__(detail)
        self.user_message = user_message


def _extract_params(build: dict[str, Any]) -> dict[str, str]:
    """Extract build parameters from Jenkins actions array.

    Jenkins stores parameters inside an actions array as:
    ``[{"parameters": [{"name": "BRANCH", "value": "main"}, ...]}, ...]``
    """
    for action in build.get("actions", []):
        params = action.get("parameters")
        if params:
            return {p["name"]: p["value"] for p in params}
    return {}


def _extract_commit_hash(build: dict[str, Any]) -> str:
    """Extract commit hash from Jenkins Git plugin's ``lastBuiltRevision``.

    The Git plugin stores the commit SHA inside the build's ``actions`` array
    as ``{"lastBuiltRevision": {"SHA1": "<hex>"}}``.  Returns an empty string
    if not present (e.g. build is still running, or Git plugin is absent).
    """
    for action in build.get("actions", []):
        rev = action.get("lastBuiltRevision", {})
        if "SHA1" in rev:
            return rev["SHA1"]
    return ""


@dataclass(frozen=True)
class JenkinsBuild:
    """Parsed build info from Jenkins REST API."""

    number: int
    result: str  # "SUCCESS", "FAILURE", "ABORTED", or "" if still building
    building: bool
    timestamp: float  # Unix seconds
    duration_ms: int  # milliseconds (0 if still building)
    branch: str
    commit_hash: str
    request_id: str


class JenkinsClient:
    """Triggers parameterised Jenkins builds and queries build history."""

    def __init__(
        self,
        url: str,
        user: str,
        api_token: str,
        job_name: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = url.rstrip("/")
        self.job_name = job_name
        self._auth = httpx.BasicAuth(user, api_token)
        self._client = client or httpx.AsyncClient(auth=self._auth)

    @property
    def job_url(self) -> str:
        return f"{self.base_url}/job/{self.job_name}"

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def get_builds(self, count: int = 20) -> list[JenkinsBuild]:
        """Fetch recent builds from Jenkins with their parameters.

        Returns up to ``count`` builds.  The caller is responsible for
        filtering to only build-manager-triggered builds (by matching
        ``request_id``).
        """
        tree = (
            "builds[number,result,building,timestamp,duration,"
            f"actions[parameters[name,value],lastBuiltRevision[SHA1]]]{{0,{count}}}"
        )
        url = f"{self.job_url}/api/json?tree={tree}"

        try:
            resp = await self._client.get(url)
            if resp.status_code != 200:
                logger.error(
                    "Jenkins get_builds failed: %d — %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return []

            data = resp.json()
            builds: list[JenkinsBuild] = []
            for raw in data.get("builds", []):
                params = _extract_params(raw)
                builds.append(
                    JenkinsBuild(
                        number=raw.get("number", 0),
                        result=raw.get("result") or "",
                        building=raw.get("building", False),
                        timestamp=raw.get("timestamp", 0) / 1000,  # ms → s
                        duration_ms=raw.get("duration", 0),
                        branch=params.get("BRANCH", ""),
                        # commit_hash is populated from the Jenkins Git
                        # plugin's lastBuiltRevision action when available.
                        commit_hash=_extract_commit_hash(raw),
                        request_id=params.get("BUILD_REQUEST_ID", ""),
                    )
                )
            return builds

        except Exception:
            logger.exception("Failed to query Jenkins builds")
            return []

    async def trigger_build(
        self,
        branch: str,
        request_id: str,
    ) -> int:
        """Trigger a parameterised Jenkins build.

        Returns the queue item ID on success.

        Raises ``JenkinsTriggerError`` with a user-friendly message on
        failure.
        """
        url = f"{self.job_url}/buildWithParameters"
        params = {
            "BRANCH": branch,
            "BUILD_REQUEST_ID": request_id,
        }

        try:
            resp = await self._client.post(url, params=params)
        except httpx.ConnectError as exc:
            logger.exception("Jenkins unreachable during build trigger")
            raise JenkinsTriggerError(
                detail=f"Connection failed: {exc}",
                user_message=(
                    "The build server isn't responding. Try again in a few minutes."
                ),
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error triggering Jenkins build")
            raise JenkinsTriggerError(
                detail=f"Unexpected error: {exc}",
                user_message=(
                    "Couldn't start the build. Try again, or contact your admin."
                ),
            ) from exc

        if resp.status_code == 201:
            queue_url = resp.headers.get("Location", "")
            try:
                queue_id = int(queue_url.rstrip("/").split("/")[-1])
                logger.info("Build queued: queue_id=%d", queue_id)
                return queue_id
            except (ValueError, IndexError) as exc:
                logger.exception("Could not parse queue ID from: %s", queue_url)
                raise JenkinsTriggerError(
                    detail=f"Bad queue URL: {queue_url}",
                    user_message=(
                        "The build was queued but something went wrong. "
                        "Try again, or contact your admin."
                    ),
                ) from exc

        if resp.status_code in (401, 403):
            logger.error(
                "Jenkins auth failure on trigger: %d — %s",
                resp.status_code,
                resp.text[:200],
            )
            raise JenkinsTriggerError(
                detail=f"Auth failure: {resp.status_code}",
                user_message=(
                    "The build server rejected the request. "
                    "Contact your admin to check credentials."
                ),
            )

        logger.error(
            "Jenkins trigger failed: %d — %s",
            resp.status_code,
            resp.text[:200],
        )
        raise JenkinsTriggerError(
            detail=f"HTTP {resp.status_code}",
            user_message=(
                "Couldn't start the build. Try again, or contact your admin."
            ),
        )

    async def check_connection(self) -> tuple[bool, int | None]:
        """Check if the Jenkins job is reachable and fetch its estimated duration.

        Returns a tuple of ``(reachable, estimated_duration_ms)``.  The
        duration is the job-level default estimate provided by Jenkins
        (in milliseconds), or ``None`` if unavailable.
        """
        url = f"{self.job_url}/api/json?tree=name,estimatedDuration"
        try:
            resp = await self._client.get(url)
            if resp.status_code != 200:
                return False, None
            data = resp.json()
            estimated = data.get("estimatedDuration")
            if isinstance(estimated, int) and estimated > 0:
                return True, estimated
            return True, None
        except Exception:
            return False, None

    async def cancel_build(self, queue_id: int) -> None:
        """Cancel a Jenkins build by queue ID.

        Tries cancelling from the queue first (if still waiting),
        then falls back to stopping a running build.
        """
        # 1. Try to cancel from the queue
        cancel_url = f"{self.base_url}/queue/cancelItem?id={queue_id}"
        resp = await self._client.post(cancel_url)
        if resp.status_code in (200, 204, 302):
            logger.info("Cancelled queued build: queue_id=%d", queue_id)
            return

        # 2. If already running, resolve the build number and stop it
        queue_info_url = f"{self.base_url}/queue/item/{queue_id}/api/json"
        resp = await self._client.get(queue_info_url)
        if resp.status_code != 200:
            logger.error(
                "Could not resolve queue item %d: %d — %s",
                queue_id,
                resp.status_code,
                resp.text[:200],
            )
            return

        data = resp.json()
        executable = data.get("executable")
        if not executable or "number" not in executable:
            logger.error(
                "Queue item %d has no executable yet — cannot stop",
                queue_id,
            )
            return

        build_number = executable["number"]
        stop_url = f"{self.job_url}/{build_number}/stop"
        resp = await self._client.post(stop_url)
        if resp.status_code in (200, 302):
            logger.info(
                "Stopped running build: %s #%d",
                self.job_name,
                build_number,
            )
        else:
            logger.error(
                "Failed to stop build %s #%d: %d — %s",
                self.job_name,
                build_number,
                resp.status_code,
                resp.text[:200],
            )

    async def download_artifact(
        self, build_number: int, pattern: str = "*.apk"
    ) -> tuple[str, bytes] | None:
        """Download the first archived artifact matching a glob pattern.

        Lists artifacts via the Jenkins REST API, then downloads the first
        file whose basename matches ``pattern`` (e.g. ``*.apk``).

        Returns ``(filename, content_bytes)`` or ``None`` if no match found.
        """
        list_url = (
            f"{self.job_url}/{build_number}/api/json"
            f"?tree=artifacts[relativePath]"
        )
        resp = await self._client.get(list_url)
        resp.raise_for_status()

        artifacts = resp.json().get("artifacts", [])
        match = None
        for art in artifacts:
            rel_path = art.get("relativePath", "")
            if fnmatch.fnmatch(rel_path.split("/")[-1], pattern):
                match = rel_path
                break

        if match is None:
            return None

        dl_url = f"{self.job_url}/{build_number}/artifact/{match}"
        resp = await self._client.get(dl_url)
        resp.raise_for_status()
        filename = match.split("/")[-1]
        return filename, resp.content
