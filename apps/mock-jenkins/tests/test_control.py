"""Smoke tests for mock-jenkins endpoints."""


def test_mock_jenkins_boots(client):
    """Mock Jenkins server boots and serves the API."""
    # The main mock-jenkins app serves Jenkins API at /job/...
    # A basic liveness check: app created without errors
    assert client.app is not None


def test_mock_agent_control_status():
    """Mock agent-control boots and serves /control/status."""
    import os
    from fastapi.testclient import TestClient
    from mock_jenkins.agent import create_app

    os.environ.setdefault("JFB_DATA_DIR", "/tmp/mock-test")
    app = create_app()
    agent_client = TestClient(app)

    resp = agent_client.get("/control/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
