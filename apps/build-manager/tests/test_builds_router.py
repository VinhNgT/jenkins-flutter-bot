"""Tests for /api/builds/* routes."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from build_manager.builds.coordinator import BuildCoordinator
from build_manager.builds.jenkins_client import JenkinsTriggerError
from build_manager.builds.state import BuildTracker


@pytest.fixture(autouse=True)
def isolate_config(tmp_path):
    os.environ["JFB_DATA_DIR"] = str(tmp_path)
    yield tmp_path
    os.environ.pop("JFB_DATA_DIR", None)


@pytest.fixture
def mock_coordinator(tmp_path):
    """Create a mock coordinator with a real tracker."""
    coord = MagicMock(spec=BuildCoordinator)
    coord.tracker = BuildTracker(tmp_path)
    coord.trigger_build = AsyncMock()
    coord.cancel_build = AsyncMock()
    return coord


@pytest.fixture
def client(mock_coordinator):
    from build_manager.main import create_app

    app = create_app()
    # Replace the coordinator via the manager
    app.state.manager._coordinator = mock_coordinator
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /api/builds/trigger
# ---------------------------------------------------------------------------


def test_trigger_missing_branch_400(client, mock_coordinator):
    resp = client.post("/api/builds/trigger", json={"branch": ""})
    assert resp.status_code == 400


def test_trigger_success(client, mock_coordinator):
    mock_coordinator.trigger_build.return_value = {
        "request_id": "abc123",
        "status": "queued",
    }
    resp = client.post("/api/builds/trigger", json={"branch": "main"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_trigger_success_with_app_name(client, mock_coordinator):
    mock_coordinator.trigger_build.return_value = {
        "request_id": "abc123",
        "status": "queued",
    }
    resp = client.post(
        "/api/builds/trigger",
        json={"branch": "main", "callback_url": "http://bot/cb", "app_name": "My App"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    mock_coordinator.trigger_build.assert_called_with(
        "main", frontend_callback_url="http://bot/cb", app_name="My App"
    )


def test_trigger_queue_full_502(client, mock_coordinator):
    mock_coordinator.trigger_build.side_effect = JenkinsTriggerError(
        "Queue full", "Build queue is full"
    )
    resp = client.post("/api/builds/trigger", json={"branch": "main"})
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET /api/builds/pending
# ---------------------------------------------------------------------------


def test_list_pending_empty(client, mock_coordinator):
    resp = client.get("/api/builds/pending")
    assert resp.status_code == 200
    assert resp.json()["builds"] == {}


def test_list_pending_with_data(client, mock_coordinator):
    mock_coordinator.tracker.add_pending("req1", "main", queue_id=1)
    resp = client.get("/api/builds/pending")
    data = resp.json()
    assert "req1" in data["builds"]
    assert data["builds"]["req1"]["branch"] == "main"


# ---------------------------------------------------------------------------
# POST /api/builds/{id}/cancel
# ---------------------------------------------------------------------------


def test_cancel_not_found_404(client, mock_coordinator):
    mock_coordinator.cancel_build.return_value = {"status": "not_found"}
    resp = client.post("/api/builds/unknown/cancel")
    assert resp.status_code == 404


def test_cancel_success(client, mock_coordinator):
    mock_coordinator.cancel_build.return_value = {"status": "cancelled"}
    resp = client.post("/api/builds/req1/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# GET /api/builds/status
# ---------------------------------------------------------------------------


def test_build_status_response(client, mock_coordinator):
    resp = client.get("/api/builds/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "pending_count" in data
