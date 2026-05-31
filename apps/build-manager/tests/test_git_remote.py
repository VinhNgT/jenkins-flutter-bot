"""Tests for the GitLab remote client (branch HEAD queries)."""

from __future__ import annotations


import httpx

from build_manager.builds.git_remote import GitRemoteClient


def _gitlab_handler(request: httpx.Request) -> httpx.Response:
    """Mock GitLab API that handles a few known branches."""
    url = str(request.url)

    if "/branches/main" in url:
        return httpx.Response(200, json={
            "name": "main",
            "commit": {"id": "abc123def456789012345678901234567890abcd"},
        })

    if "/branches/feature%2Fslash" in url:
        return httpx.Response(200, json={
            "name": "feature/slash",
            "commit": {"id": "def456abc789012345678901234567890abcd1234"},
        })

    if "/branches/no-commit" in url:
        return httpx.Response(200, json={"name": "no-commit"})

    if "/branches/empty-id" in url:
        return httpx.Response(200, json={
            "name": "empty-id",
            "commit": {"id": ""},
        })

    if "/branches/server-error" in url:
        return httpx.Response(500, text="Internal Server Error")

    return httpx.Response(404, json={"message": "404 Branch Not Found"})


def _make_client(
    base_url: str = "https://gitlab.example.com",
    project_id: str = "my-group/my-project",
    token: str = "test-token",
) -> GitRemoteClient:
    """Create a GitRemoteClient with a mock transport."""
    return GitRemoteClient(
        base_url=base_url,
        project_id=project_id,
        token=token,
        client=httpx.AsyncClient(transport=httpx.MockTransport(_gitlab_handler)),
    )


class TestGetBranchHead:
    """Tests for GitRemoteClient.get_branch_head()."""

    async def test_returns_sha_for_known_branch(self) -> None:
        client = _make_client()
        sha = await client.get_branch_head("main")
        assert sha == "abc123def456789012345678901234567890abcd"

    async def test_returns_none_for_unknown_branch(self) -> None:
        client = _make_client()
        sha = await client.get_branch_head("nonexistent")
        assert sha is None

    async def test_returns_none_on_server_error(self) -> None:
        client = _make_client()
        sha = await client.get_branch_head("server-error")
        assert sha is None

    async def test_url_encodes_branch_name(self) -> None:
        """Branch names with slashes must be URL-encoded."""
        client = _make_client()
        sha = await client.get_branch_head("feature/slash")
        assert sha == "def456abc789012345678901234567890abcd1234"

    async def test_url_encodes_project_id(self) -> None:
        """Project paths with slashes are encoded (my-group/my-project → my-group%2Fmy-project)."""
        # The mock handler receives the request with encoded path segments
        client = _make_client(project_id="my-group/my-project")
        sha = await client.get_branch_head("main")
        assert sha is not None

    async def test_returns_none_when_commit_missing(self) -> None:
        """Response without 'commit' key returns None."""
        client = _make_client()
        sha = await client.get_branch_head("no-commit")
        assert sha is None

    async def test_returns_none_when_commit_id_empty(self) -> None:
        """Empty commit id string returns None."""
        client = _make_client()
        sha = await client.get_branch_head("empty-id")
        assert sha is None

    async def test_sends_private_token_header(self) -> None:
        """When token is set, PRIVATE-TOKEN header is included."""
        captured_headers: dict[str, str] = {}

        def capture_handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={
                "name": "main",
                "commit": {"id": "abc123def456789012345678901234567890abcd"},
            })

        client = GitRemoteClient(
            base_url="https://gitlab.example.com",
            project_id="1234",
            token="my-private-token",
            client=httpx.AsyncClient(transport=httpx.MockTransport(capture_handler)),
        )
        await client.get_branch_head("main")
        assert captured_headers.get("private-token") == "my-private-token"

    async def test_no_token_omits_header(self) -> None:
        """When token is empty, no PRIVATE-TOKEN header is sent."""
        captured_headers: dict[str, str] = {}

        def capture_handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={
                "name": "main",
                "commit": {"id": "abc123def456789012345678901234567890abcd"},
            })

        client = GitRemoteClient(
            base_url="https://gitlab.example.com",
            project_id="1234",
            token="",
            client=httpx.AsyncClient(transport=httpx.MockTransport(capture_handler)),
        )
        await client.get_branch_head("main")
        assert "private-token" not in captured_headers

    async def test_network_error_returns_none(self) -> None:
        """Connection failure returns None instead of raising."""
        def error_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = GitRemoteClient(
            base_url="https://gitlab.example.com",
            project_id="123",
            client=httpx.AsyncClient(transport=httpx.MockTransport(error_handler)),
        )
        sha = await client.get_branch_head("main")
        assert sha is None

    async def test_malformed_json_returns_none(self) -> None:
        """Invalid JSON response returns None."""
        def bad_json_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json", headers={"content-type": "application/json"})

        client = GitRemoteClient(
            base_url="https://gitlab.example.com",
            project_id="123",
            client=httpx.AsyncClient(transport=httpx.MockTransport(bad_json_handler)),
        )
        sha = await client.get_branch_head("main")
        assert sha is None


class TestClose:
    """Tests for client cleanup."""

    async def test_close_does_not_raise(self) -> None:
        client = _make_client()
        await client.close()
