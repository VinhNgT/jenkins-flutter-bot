"""GitLab API client for querying branch HEAD commits."""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# Request timeout — fast enough to not block /build noticeably,
# long enough for high-latency self-hosted instances.
_TIMEOUT = 5.0


class GitRemoteClient:
    """Queries a GitLab instance for the latest commit on a branch.

    Used by the build handler to detect duplicate builds — if the remote
    HEAD matches the last built commit, the build is redundant.

    All methods are fail-safe: network errors, auth failures, and
    unexpected responses return ``None`` rather than raising.  The caller
    treats ``None`` as "unknown" and proceeds with the build.
    """

    def __init__(
        self, base_url: str, project_id: str, token: str = ""
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # URL-encode the project path (slashes → %2F).
        # Numeric IDs pass through unchanged.
        self._project_id = quote(project_id, safe="")
        self._token = token
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)

    async def get_branch_head(self, branch: str) -> str | None:
        """Return the HEAD commit SHA of a remote branch, or None on failure.

        Calls the GitLab Branches API:
            GET /api/v4/projects/{id}/repository/branches/{branch}

        Returns the full 40-character commit SHA from ``commit.id``,
        or ``None`` if the request fails for any reason.
        """
        encoded_branch = quote(branch, safe="")
        url = (
            f"{self._base_url}/api/v4/projects/{self._project_id}"
            f"/repository/branches/{encoded_branch}"
        )

        headers: dict[str, str] = {}
        if self._token:
            headers["PRIVATE-TOKEN"] = self._token

        try:
            resp = await self._client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.debug(
                    "GitLab branch query failed: %d — %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None

            data = resp.json()
            commit = data.get("commit", {})
            sha: str = commit.get("id", "")
            return sha or None

        except Exception:
            logger.exception("Failed to query GitLab for branch HEAD")
            return None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
