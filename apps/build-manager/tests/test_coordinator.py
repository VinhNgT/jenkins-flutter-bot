"""Tests for BuildCoordinator — full lifecycle, timeout, cancellation."""

from unittest.mock import AsyncMock

import httpx
import pytest

from build_manager.builds.coordinator import BuildCoordinator
from build_manager.builds.jenkins_client import (
    JenkinsBuild,
    JenkinsClient,
    JenkinsTriggerError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_jenkins(
    *,
    trigger_queue_id: int = 42,
    builds: list[JenkinsBuild] | None = None,
    artifact: tuple[str, bytes] | None = None,
) -> JenkinsClient:
    """Create a mock JenkinsClient."""
    mock = AsyncMock(spec=JenkinsClient)
    mock.trigger_build = AsyncMock(return_value=trigger_queue_id)
    mock.get_builds = AsyncMock(return_value=builds or [])
    mock.download_artifact = AsyncMock(return_value=artifact)
    mock.cancel_build = AsyncMock()
    mock.close = AsyncMock()
    mock.job_name = "flutter-build"
    return mock


def _file_manager_handler(request: httpx.Request):
    """Mock file-manager HTTP handler.

    Responds to both the new ``POST /api/files/builds/record`` endpoint
    and file DELETE requests.
    """
    if "builds/record" in str(request.url):
        return httpx.Response(200, json={
            "status": "recorded",
            "download_url": "https://drive.google.com/file/123",
            "file_id": "drive_file_123",
        })
    if request.method == "DELETE":
        return httpx.Response(200, json={"status": "deleted"})
    return httpx.Response(200, json={})


def _frontend_handler(request: httpx.Request):
    """Mock frontend callback handler."""
    return httpx.Response(200, json={"status": "ok"})


@pytest.fixture
def coordinator(tmp_path):
    """Create a BuildCoordinator with mocked dependencies."""
    jenkins = _mock_jenkins()
    transport = httpx.MockTransport(_file_manager_handler)
    http = httpx.AsyncClient(transport=transport)
    clock_time = [1_700_000_000.0]

    coord = BuildCoordinator(
        data_dir=tmp_path,
        jenkins=jenkins,
        file_manager_url="http://file-manager:9092",
        build_timeout=30,
        poll_interval=1,
        http_client=http,
        clock=lambda: clock_time[0],
    )
    coord._clock_ref = clock_time  # expose for test manipulation
    return coord


# ---------------------------------------------------------------------------
# trigger_build
# ---------------------------------------------------------------------------


class TestTriggerBuild:
    async def test_registers_pending_and_starts_poll(self, coordinator):
        result = await coordinator.trigger_build("main", frontend_callback_url="http://bot/cb")
        assert result["status"] == "queued"
        assert "request_id" in result
        assert coordinator.tracker.pending_count == 1
        assert len(coordinator._poll_tasks) == 1
        await coordinator.close()

    async def test_jenkins_trigger_failure_propagates(self, tmp_path):
        jenkins = _mock_jenkins()
        jenkins.trigger_build = AsyncMock(
            side_effect=JenkinsTriggerError("boom", "Jenkins is down")
        )
        coord = BuildCoordinator(
            data_dir=tmp_path,
            jenkins=jenkins,
            file_manager_url="http://fm:9092",
        )
        with pytest.raises(JenkinsTriggerError):
            await coord.trigger_build("main")
        assert coord.tracker.pending_count == 0
        await coord.close()


# ---------------------------------------------------------------------------
# _complete_build
# ---------------------------------------------------------------------------


class TestCompleteBuild:
    async def test_success_sends_record_to_file_manager(self, coordinator):
        # Setup: add a pending build
        coordinator._jenkins.trigger_build = AsyncMock(return_value=42)
        result = await coordinator.trigger_build(
            "main", frontend_callback_url="http://bot/cb"
        )
        request_id = result["request_id"]

        # Mock artifact download
        coordinator._jenkins.download_artifact = AsyncMock(
            return_value=("app-release.apk", b"apk-data")
        )

        # Simulate build completion
        jenkins_build = JenkinsBuild(
            number=1, result="SUCCESS", building=False,
            timestamp=1_700_000_000.0, duration_ms=60000,
            branch="main", commit_hash="a" * 40, request_id=request_id,
        )
        await coordinator._complete_build(request_id, jenkins_build)

        # Pending should be consumed
        assert coordinator.tracker.get_pending(request_id) is None
        await coordinator.close()

    async def test_success_derives_filename_from_app_name(self, coordinator):
        # Setup: add a pending build with app_name
        coordinator._jenkins.trigger_build = AsyncMock(return_value=42)
        result = await coordinator.trigger_build(
            "main", frontend_callback_url="http://bot/cb", app_name="My Awesome App!"
        )
        request_id = result["request_id"]

        # Mock artifact download
        coordinator._jenkins.download_artifact = AsyncMock(
            return_value=("app-release.apk", b"apk-data")
        )

        # Mock _record_build to capture the call
        coordinator._record_build = AsyncMock(
            return_value={"download_url": "https://drive.google.com/file/123", "file_id": "drive_file_123"}
        )

        # Simulate build completion
        jenkins_build = JenkinsBuild(
            number=1, result="SUCCESS", building=False,
            timestamp=1_700_000_000.0, duration_ms=60000,
            branch="main", commit_hash="a" * 40, request_id=request_id,
        )
        await coordinator._complete_build(request_id, jenkins_build)

        # Verify that _record_build was called with artifact containing derived filename
        assert coordinator._record_build.called
        call_kwargs = coordinator._record_build.call_args.kwargs
        artifact = call_kwargs["artifact"]
        assert artifact is not None
        filename, content = artifact
        # Expected pattern: my-awesome-app-{YYYYMMDD}-{HHmmss}-{requestId8}.apk
        assert filename.startswith("my-awesome-app-")
        assert filename.endswith(f"-{request_id[:8]}.apk")
        await coordinator.close()

    async def test_failure_no_upload(self, coordinator):
        result = await coordinator.trigger_build("main")
        request_id = result["request_id"]

        jenkins_build = JenkinsBuild(
            number=1, result="FAILURE", building=False,
            timestamp=1_700_000_000.0, duration_ms=60000,
            branch="main", commit_hash="a" * 40, request_id=request_id,
        )
        await coordinator._complete_build(request_id, jenkins_build)

        coordinator._jenkins.download_artifact.assert_not_awaited()
        await coordinator.close()

    async def test_already_consumed_is_noop(self, coordinator):
        """If pending was already consumed (e.g. cancelled), _complete_build is a no-op."""
        result = await coordinator.trigger_build("main")
        request_id = result["request_id"]
        coordinator.tracker.consume_pending(request_id)

        jenkins_build = JenkinsBuild(
            number=1, result="SUCCESS", building=False,
            timestamp=1_700_000_000.0, duration_ms=60000,
            branch="main", commit_hash="a" * 40, request_id=request_id,
        )
        await coordinator._complete_build(request_id, jenkins_build)
        await coordinator.close()


# ---------------------------------------------------------------------------
# _handle_timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    async def test_records_timeout(self, coordinator):
        result = await coordinator.trigger_build("main")
        request_id = result["request_id"]

        await coordinator._handle_timeout(request_id)

        # Pending should be consumed
        assert coordinator.tracker.get_pending(request_id) is None
        await coordinator.close()

    async def test_timeout_already_consumed(self, coordinator):
        result = await coordinator.trigger_build("main")
        request_id = result["request_id"]
        coordinator.tracker.consume_pending(request_id)

        # Should be a no-op (no crash)
        await coordinator._handle_timeout(request_id)
        await coordinator.close()


# ---------------------------------------------------------------------------
# _record_build
# ---------------------------------------------------------------------------


class TestRecordBuild:
    async def test_sends_metadata_to_file_manager(self, coordinator):
        """Verify _record_build sends proper form data."""
        result = await coordinator._record_build(
            request_id="req1",
            branch="main",
            commit_hash="a" * 40,
            result="success",
            triggered_at=1.0,
            completed_at=2.0,
        )
        assert result["status"] == "recorded"
        await coordinator.close()

    async def test_sends_artifact_with_metadata(self, coordinator):
        """Verify artifact is included when provided."""
        result = await coordinator._record_build(
            request_id="req1",
            branch="main",
            commit_hash="a" * 40,
            result="success",
            triggered_at=1.0,
            completed_at=2.0,
            artifact=("test.apk", b"fake-apk-data"),
        )
        assert result["status"] == "recorded"
        assert result["download_url"] == "https://drive.google.com/file/123"
        await coordinator.close()

    async def test_failure_returns_empty_dict(self, tmp_path):
        """When file-manager is down, returns empty dict (best-effort)."""
        def error_handler(request: httpx.Request):
            return httpx.Response(500, text="Server Error")

        jenkins = _mock_jenkins()
        transport = httpx.MockTransport(error_handler)
        http = httpx.AsyncClient(transport=transport)
        coord = BuildCoordinator(
            data_dir=tmp_path,
            jenkins=jenkins,
            file_manager_url="http://fm:9092",
            http_client=http,
        )

        result = await coord._record_build(
            request_id="req1",
            branch="main",
            commit_hash="a" * 40,
            result="success",
            triggered_at=1.0,
            completed_at=2.0,
        )
        assert result == {}
        await coord.close()


# ---------------------------------------------------------------------------
# _notify_frontend
# ---------------------------------------------------------------------------


class TestNotifyFrontend:
    async def test_failure_logged_not_raised(self, tmp_path):
        def error_handler(request: httpx.Request):
            return httpx.Response(500, text="Server Error")

        jenkins = _mock_jenkins()
        transport = httpx.MockTransport(error_handler)
        http = httpx.AsyncClient(transport=transport)
        coord = BuildCoordinator(
            data_dir=tmp_path,
            jenkins=jenkins,
            file_manager_url="http://fm:9092",
            http_client=http,
        )

        # Should not raise
        await coord._notify_frontend(
            "http://bot:9090/callback",
            request_id="req1",
            branch="main",
            commit_hash="a" * 40,
            result="success",
            triggered_at=1.0,
            completed_at=2.0,
        )
        await coord.close()


# ---------------------------------------------------------------------------
# cancel_build
# ---------------------------------------------------------------------------


class TestCancelBuild:
    async def test_stops_poll_task(self, coordinator):
        result = await coordinator.trigger_build("main")
        request_id = result["request_id"]
        assert request_id in coordinator._poll_tasks

        cancel_result = await coordinator.cancel_build(request_id)
        assert cancel_result["status"] == "cancelled"
        assert request_id not in coordinator._poll_tasks
        assert coordinator.tracker.get_pending(request_id) is None
        await coordinator.close()

    async def test_cancel_not_found(self, coordinator):
        result = await coordinator.cancel_build("nonexistent")
        assert result["status"] == "not_found"
        await coordinator.close()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    async def test_cancels_all_poll_tasks(self, coordinator):
        await coordinator.trigger_build("branch-a")
        await coordinator.trigger_build("branch-b")
        assert len(coordinator._poll_tasks) == 2

        await coordinator.close()
        assert len(coordinator._poll_tasks) == 0
