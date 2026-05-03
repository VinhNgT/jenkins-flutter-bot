"""Jenkins REST API client for triggering and querying builds."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class JenkinsClient:
    """Triggers parameterized Jenkins builds and queries build history."""

    def __init__(self, url: str, user: str, api_token: str, job_name: str) -> None:
        self.base_url = url.rstrip("/")
        self.job_name = job_name
        self._auth = httpx.BasicAuth(user, api_token)
        self._client = httpx.AsyncClient(auth=self._auth)

    @property
    def job_url(self) -> str:
        return f"{self.base_url}/job/{self.job_name}"

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def trigger_build(
        self,
        branch: str,
        callback_url: str,
        request_id: str,
        job_id: str,
    ) -> int | None:
        """Trigger a parameterized Jenkins build.

        Returns the queue item ID, or None on failure.
        """
        url = f"{self.job_url}/buildWithParameters"
        params = {
            "BRANCH": branch,
            "BOT_CALLBACK_URL": callback_url,
            "BOT_REQUEST_ID": request_id,
            "BOT_JOB_ID": job_id,
        }

        resp = await self._client.post(url, params=params)
        if resp.status_code == 201:
            queue_url = resp.headers.get("Location", "")
            try:
                queue_id = int(queue_url.rstrip("/").split("/")[-1])
                logger.info("Build queued: queue_id=%d", queue_id)
                return queue_id
            except (ValueError, IndexError):
                logger.error("Could not parse queue ID from: %s", queue_url)
                return None
        else:
            logger.error(
                "Jenkins trigger failed: %d — %s",
                resp.status_code,
                resp.text[:200],
            )
            return None

    async def get_recent_builds(self, count: int = 5) -> list[dict]:
        """Get recent build history for /recent command."""
        url = (
            f"{self.job_url}/api/json"
            f"?tree=builds[number,result,timestamp,duration]"
            f"{{0,{count}}}"
        )
        resp = await self._client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("builds", [])
        return []
