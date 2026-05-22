"""Tests for JenkinsClient — HTTP error handling and response parsing."""

import pytest
import httpx

from build_manager.builds.jenkins_client import (
    JenkinsClient,
    JenkinsBuild,
    JenkinsTriggerError,
    _extract_params,
    _extract_commit_hash,
)


# ---------------------------------------------------------------------------
# Helpers for building mock responses
# ---------------------------------------------------------------------------


def _jenkins_client(handler) -> JenkinsClient:
    """Create a JenkinsClient backed by MockTransport."""
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return JenkinsClient(
        url="http://jenkins:8080",
        user="admin",
        api_token="fake-token",
        job_name="flutter-build",
        client=client,
    )


def _build_json(
    number=1,
    result="SUCCESS",
    building=False,
    branch="main",
    request_id="abc123",
    commit_hash="a" * 40,
) -> dict:
    """Build a Jenkins API build JSON object."""
    actions = [
        {
            "parameters": [
                {"name": "BRANCH", "value": branch},
                {"name": "BUILD_REQUEST_ID", "value": request_id},
            ]
        },
    ]
    if commit_hash and not building:
        actions.append({"lastBuiltRevision": {"SHA1": commit_hash}})
    return {
        "number": number,
        "result": None if building else result,
        "building": building,
        "timestamp": 1_700_000_000_000,  # ms
        "duration": 60000,
        "actions": actions,
    }


# ---------------------------------------------------------------------------
# _extract_params / _extract_commit_hash
# ---------------------------------------------------------------------------


class TestExtractors:
    def test_extract_params(self):
        build = _build_json()
        params = _extract_params(build)
        assert params["BRANCH"] == "main"
        assert params["BUILD_REQUEST_ID"] == "abc123"

    def test_extract_params_no_actions(self):
        assert _extract_params({}) == {}
        assert _extract_params({"actions": []}) == {}

    def test_extract_commit_hash(self):
        build = _build_json(commit_hash="deadbeef" * 5)
        assert _extract_commit_hash(build) == "deadbeef" * 5

    def test_extract_commit_hash_missing(self):
        build = _build_json(building=True, commit_hash="")
        assert _extract_commit_hash(build) == ""

    def test_extract_commit_hash_no_actions(self):
        assert _extract_commit_hash({}) == ""


# ---------------------------------------------------------------------------
# trigger_build
# ---------------------------------------------------------------------------


class TestTriggerBuild:
    async def test_success(self):
        def handler(request: httpx.Request):
            return httpx.Response(
                201,
                headers={"Location": "http://jenkins:8080/queue/item/42/"},
            )

        client = _jenkins_client(handler)
        queue_id = await client.trigger_build(branch="main", request_id="req1")
        assert queue_id == 42
        await client.close()

    async def test_bad_queue_url(self):
        def handler(request: httpx.Request):
            return httpx.Response(
                201,
                headers={"Location": "http://jenkins:8080/not-a-queue-url"},
            )

        client = _jenkins_client(handler)
        with pytest.raises(JenkinsTriggerError) as exc_info:
            await client.trigger_build(branch="main", request_id="req1")
        assert "user_message" in dir(exc_info.value)
        await client.close()

    async def test_auth_failure_401(self):
        def handler(request: httpx.Request):
            return httpx.Response(401, text="Unauthorized")

        client = _jenkins_client(handler)
        with pytest.raises(JenkinsTriggerError) as exc_info:
            await client.trigger_build(branch="main", request_id="req1")
        assert "credentials" in exc_info.value.user_message.lower()
        await client.close()

    async def test_auth_failure_403(self):
        def handler(request: httpx.Request):
            return httpx.Response(403, text="Forbidden")

        client = _jenkins_client(handler)
        with pytest.raises(JenkinsTriggerError):
            await client.trigger_build(branch="main", request_id="req1")
        await client.close()

    async def test_unexpected_status(self):
        def handler(request: httpx.Request):
            return httpx.Response(500, text="Internal Server Error")

        client = _jenkins_client(handler)
        with pytest.raises(JenkinsTriggerError):
            await client.trigger_build(branch="main", request_id="req1")
        await client.close()

    async def test_connection_error(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        client = _jenkins_client(handler)
        with pytest.raises(JenkinsTriggerError) as exc_info:
            await client.trigger_build(branch="main", request_id="req1")
        assert "responding" in exc_info.value.user_message.lower()
        await client.close()


# ---------------------------------------------------------------------------
# get_builds
# ---------------------------------------------------------------------------


class TestGetBuilds:
    async def test_parses_params_and_commit(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={
                "builds": [_build_json(number=1, branch="main", request_id="req1")]
            })

        client = _jenkins_client(handler)
        builds = await client.get_builds(count=10)
        assert len(builds) == 1
        assert builds[0].branch == "main"
        assert builds[0].request_id == "req1"
        assert builds[0].commit_hash == "a" * 40
        assert builds[0].number == 1
        await client.close()

    async def test_missing_params(self):
        """Build with no parameters → empty strings."""
        def handler(request: httpx.Request):
            return httpx.Response(200, json={
                "builds": [{
                    "number": 1, "result": "SUCCESS", "building": False,
                    "timestamp": 1_700_000_000_000, "duration": 0,
                    "actions": [],
                }]
            })

        client = _jenkins_client(handler)
        builds = await client.get_builds()
        assert builds[0].branch == ""
        assert builds[0].request_id == ""
        await client.close()

    async def test_non_200_returns_empty(self):
        def handler(request: httpx.Request):
            return httpx.Response(500, text="Error")

        client = _jenkins_client(handler)
        builds = await client.get_builds()
        assert builds == []
        await client.close()

    async def test_network_error_returns_empty(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        client = _jenkins_client(handler)
        builds = await client.get_builds()
        assert builds == []
        await client.close()

    async def test_building_flag(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={
                "builds": [_build_json(building=True)]
            })

        client = _jenkins_client(handler)
        builds = await client.get_builds()
        assert builds[0].building is True
        assert builds[0].result == ""
        await client.close()


# ---------------------------------------------------------------------------
# download_artifact
# ---------------------------------------------------------------------------


class TestDownloadArtifact:
    async def test_glob_match(self):
        def handler(request: httpx.Request):
            if "api/json" in str(request.url):
                return httpx.Response(200, json={
                    "artifacts": [
                        {"relativePath": "build/app/outputs/app-release.apk"}
                    ]
                })
            return httpx.Response(200, content=b"fake-apk-content")

        client = _jenkins_client(handler)
        result = await client.download_artifact(42, "*.apk")
        assert result is not None
        filename, content = result
        assert filename == "app-release.apk"
        assert content == b"fake-apk-content"
        await client.close()

    async def test_no_match(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={
                "artifacts": [{"relativePath": "build/output/report.html"}]
            })

        client = _jenkins_client(handler)
        result = await client.download_artifact(42, "*.apk")
        assert result is None
        await client.close()

    async def test_no_artifacts(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={"artifacts": []})

        client = _jenkins_client(handler)
        result = await client.download_artifact(42, "*.apk")
        assert result is None
        await client.close()


# ---------------------------------------------------------------------------
# cancel_build
# ---------------------------------------------------------------------------


class TestCancelBuild:
    async def test_cancel_from_queue(self):
        """204 response → success (no fallback needed)."""
        def handler(request: httpx.Request):
            if "cancelItem" in str(request.url):
                return httpx.Response(204)
            return httpx.Response(200, json={})

        client = _jenkins_client(handler)
        await client.cancel_build(42)  # should not raise
        await client.close()

    async def test_cancel_already_running(self):
        """Queue cancel 404 → falls back to stop."""
        call_log = []

        def handler(request: httpx.Request):
            url = str(request.url)
            call_log.append(url)
            if "cancelItem" in url:
                return httpx.Response(404)
            if "queue/item" in url:
                return httpx.Response(200, json={
                    "executable": {"number": 5, "url": "/job/test/5/"}
                })
            if "/stop" in url:
                return httpx.Response(302)
            return httpx.Response(200, json={})

        client = _jenkins_client(handler)
        await client.cancel_build(42)
        assert any("/stop" in url for url in call_log)
        await client.close()


# ---------------------------------------------------------------------------
# check_connection
# ---------------------------------------------------------------------------


class TestCheckConnection:
    async def test_ok(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={"name": "test"})

        client = _jenkins_client(handler)
        assert await client.check_connection() is True
        await client.close()

    async def test_failure(self):
        def handler(request: httpx.Request):
            return httpx.Response(403, text="Forbidden")

        client = _jenkins_client(handler)
        assert await client.check_connection() is False
        await client.close()
