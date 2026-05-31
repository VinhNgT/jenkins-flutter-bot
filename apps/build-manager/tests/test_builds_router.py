"""Tests for /api/builds/* routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from build_manager.builds.coordinator import BuildCoordinator
from build_manager.builds.jenkins_client import JenkinsTriggerError
from build_manager.builds.state import BuildTracker
from build_manager.main import create_app


@pytest.fixture
def mock_coordinator(tmp_path):
    """Create a mock coordinator with a real tracker."""
    coord = MagicMock(spec=BuildCoordinator)
    coord.tracker = BuildTracker(tmp_path)
    coord.trigger_build = AsyncMock()
    coord.cancel_build = AsyncMock()
    return coord


@pytest.fixture
async def client(mock_coordinator):
    app = create_app()
    # Replace the coordinator via the manager
    app.state.manager._coordinator = mock_coordinator
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /api/builds/trigger
# ---------------------------------------------------------------------------


async def test_trigger_missing_branch_400(client, mock_coordinator):
    resp = await client.post("/api/builds/trigger", json={"branch": ""})
    assert resp.status_code == 400


async def test_trigger_success(client, mock_coordinator):
    mock_coordinator.trigger_build.return_value = {
        "request_id": "abc123",
        "status": "queued",
    }
    resp = await client.post("/api/builds/trigger", json={"branch": "main"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


async def test_trigger_success_with_app_name(client, mock_coordinator):
    mock_coordinator.trigger_build.return_value = {
        "request_id": "abc123",
        "status": "queued",
    }
    resp = await client.post(
        "/api/builds/trigger",
        json={"branch": "main", "callback_url": "http://bot/cb", "app_name": "My App"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    mock_coordinator.trigger_build.assert_called_with(
        "main",
        frontend_callback_url="http://bot/cb",
        app_name="My App",
        label="",
        triggered_by="",
        triggered_by_id=0,
        notify=True,
        chat_id=0,
    )


async def test_trigger_queue_full_502(client, mock_coordinator):
    mock_coordinator.trigger_build.side_effect = JenkinsTriggerError(
        "Queue full", "Build queue is full"
    )
    resp = await client.post("/api/builds/trigger", json={"branch": "main"})
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET /api/builds/pending
# ---------------------------------------------------------------------------


async def test_list_pending_empty(client, mock_coordinator):
    resp = await client.get("/api/builds/pending")
    assert resp.status_code == 200
    assert resp.json()["builds"] == {}


async def test_list_pending_with_data(client, mock_coordinator):
    mock_coordinator.tracker.add_pending("req1", "main", queue_id=1)
    resp = await client.get("/api/builds/pending")
    data = resp.json()
    assert "req1" in data["builds"]
    assert data["builds"]["req1"]["branch"] == "main"


# ---------------------------------------------------------------------------
# POST /api/builds/{id}/cancel
# ---------------------------------------------------------------------------


async def test_cancel_not_found_404(client, mock_coordinator):
    mock_coordinator.cancel_build.return_value = {"status": "not_found"}
    resp = await client.post("/api/builds/unknown/cancel")
    assert resp.status_code == 404


async def test_cancel_success(client, mock_coordinator):
    mock_coordinator.cancel_build.return_value = {"status": "cancelled"}
    resp = await client.post("/api/builds/req1/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# GET /api/builds/status
# ---------------------------------------------------------------------------


async def test_build_status_response(client, mock_coordinator):
    resp = await client.get("/api/builds/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "pending_count" in data


# ---------------------------------------------------------------------------
# GET /api/builds/recent
# ---------------------------------------------------------------------------


async def test_recent_builds_success(client, mock_coordinator):
    mock_coordinator._file_manager_url = "http://file-manager"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"builds": [{"branch": "main", "result": "success"}]}
    mock_coordinator._http = AsyncMock()
    mock_coordinator._http.get.return_value = mock_response

    resp = await client.get("/api/builds/recent?count=5")
    assert resp.status_code == 200
    assert resp.json() == {"builds": [{"branch": "main", "result": "success"}]}
    mock_coordinator._http.get.assert_called_with("http://file-manager/api/files/builds/recent?count=5")


async def test_recent_builds_file_manager_error(client, mock_coordinator):
    mock_coordinator._file_manager_url = "http://file-manager"
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_coordinator._http = AsyncMock()
    mock_coordinator._http.get.return_value = mock_response

    resp = await client.get("/api/builds/recent")
    assert resp.status_code == 500
    assert "Failed to fetch recent builds from file-manager" in resp.json()["detail"]


async def test_recent_builds_file_manager_unreachable(client, mock_coordinator):
    mock_coordinator._file_manager_url = "http://file-manager"
    mock_coordinator._http = AsyncMock()
    mock_coordinator._http.get.side_effect = httpx.ConnectError("Connection refused")

    resp = await client.get("/api/builds/recent")
    assert resp.status_code == 502
    assert "file-manager is unreachable" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/builds/stream
# ---------------------------------------------------------------------------


async def test_build_stream(client, mock_coordinator):
    """Verify that the build manager streams events in SSE format."""
    mock_coordinator._file_manager_url = "http://file-manager"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"builds": []}
    mock_coordinator._http = AsyncMock()
    mock_coordinator._http.get.return_value = mock_response

    call_count = 0

    async def fake_is_disconnected(self):
        nonlocal call_count
        call_count += 1
        return call_count > 1

    original_add = mock_coordinator.tracker.add_listener

    def fake_add_listener(evt):
        original_add(evt)
        evt.set()

    # Force the SSE event listener to trigger immediately to avoid the 15-second idle wait
    mock_coordinator.tracker.add_listener = fake_add_listener

    # Mock Request.is_disconnected so the infinite SSE stream loop exits cleanly under ASGITransport
    with patch("starlette.requests.Request.is_disconnected", fake_is_disconnected):
        async with client.stream("GET", "/api/builds/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")

            lines = []
            async for line in response.aiter_lines():
                lines.append(line)
                if not line:
                    break

            event_content = "\n".join(lines)
            assert "event: builds" in event_content
