import httpx
import pytest
from unittest.mock import AsyncMock

from build_manager.builds.coordinator import BuildCoordinator
from build_manager.builds.jenkins_client import JenkinsBuild, JenkinsClient


def _mock_jenkins() -> JenkinsClient:
    mock = AsyncMock(spec=JenkinsClient)
    mock.trigger_build = AsyncMock(return_value=42)
    mock.get_builds = AsyncMock(return_value=[])
    mock.download_artifact = AsyncMock(return_value=None)
    mock.cancel_build = AsyncMock()
    mock.close = AsyncMock()
    mock.job_name = "flutter-build"
    return mock


@pytest.mark.asyncio
async def test_coordinator_vpn_connect_on_trigger(tmp_path):
    jenkins = _mock_jenkins()

    vpn_calls = []

    def mock_handler(request: httpx.Request):
        if "vpn/connect" in str(request.url):
            vpn_calls.append("connect")
            return httpx.Response(200, json={"status": "connecting"})
        return httpx.Response(200, json={})

    http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    coord = BuildCoordinator(
        data_dir=tmp_path,
        jenkins=jenkins,
        file_manager_url="http://fm:9092",
        agent_control_url="http://agent-control:9091",
        http_client=http,
    )

    await coord.trigger_build("main")
    assert "connect" in vpn_calls
    await coord.close()


@pytest.mark.asyncio
async def test_coordinator_vpn_disconnect_when_idle(tmp_path):
    jenkins = _mock_jenkins()

    vpn_calls = []

    def mock_handler(request: httpx.Request):
        if "vpn/connect" in str(request.url):
            vpn_calls.append("connect")
            return httpx.Response(200, json={"status": "connecting"})
        if "vpn/disconnect" in str(request.url):
            vpn_calls.append("disconnect")
            return httpx.Response(200, json={"status": "disconnected"})
        return httpx.Response(200, json={})

    http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    coord = BuildCoordinator(
        data_dir=tmp_path,
        jenkins=jenkins,
        file_manager_url="http://fm:9092",
        agent_control_url="http://agent-control:9091",
        http_client=http,
    )

    # 1. Trigger first build
    result1 = await coord.trigger_build("main")
    req1 = result1["request_id"]

    # 2. Trigger second build
    result2 = await coord.trigger_build("dev")
    req2 = result2["request_id"]

    assert vpn_calls == ["connect", "connect"]  # connect called for each trigger

    # 3. Complete first build -> pending_count is 1 -> no disconnect
    jenkins_build1 = JenkinsBuild(
        number=1,
        result="SUCCESS",
        building=False,
        timestamp=1000.0,
        duration_ms=10000,
        branch="main",
        commit_hash="a" * 40,
        request_id=req1,
    )
    await coord._complete_build(req1, jenkins_build1)
    assert "disconnect" not in vpn_calls

    # 4. Complete second build -> pending_count is 0 -> should disconnect!
    jenkins_build2 = JenkinsBuild(
        number=2,
        result="SUCCESS",
        building=False,
        timestamp=1000.0,
        duration_ms=10000,
        branch="dev",
        commit_hash="b" * 40,
        request_id=req2,
    )
    await coord._complete_build(req2, jenkins_build2)
    assert "disconnect" in vpn_calls

    await coord.close()


@pytest.mark.asyncio
async def test_coordinator_vpn_best_effort(tmp_path):
    jenkins = _mock_jenkins()

    def mock_handler(request: httpx.Request):
        # Return 500 error for VPN calls
        return httpx.Response(500, text="Internal Server Error")

    http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    coord = BuildCoordinator(
        data_dir=tmp_path,
        jenkins=jenkins,
        file_manager_url="http://fm:9092",
        agent_control_url="http://agent-control:9091",
        http_client=http,
    )

    # Trigger build should still succeed even if VPN connect fails
    result = await coord.trigger_build("main")
    assert result["status"] == "queued"

    # Complete build should still succeed even if VPN disconnect fails
    req_id = result["request_id"]
    jenkins_build = JenkinsBuild(
        number=1,
        result="SUCCESS",
        building=False,
        timestamp=1000.0,
        duration_ms=10000,
        branch="main",
        commit_hash="a" * 40,
        request_id=req_id,
    )
    await coord._complete_build(req_id, jenkins_build)

    await coord.close()
