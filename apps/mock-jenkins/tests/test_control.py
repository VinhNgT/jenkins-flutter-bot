"""Smoke tests for mock-jenkins endpoints."""

from __future__ import annotations

import httpx

from mock_jenkins.agent import create_app as create_agent_app


async def test_mock_jenkins_boots(client):
    """Mock Jenkins server boots and serves the API."""
    assert client is not None


async def test_mock_agent_control_status():
    """Mock agent-control boots and serves /control/status."""
    app = create_agent_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as agent_client:
        resp = await agent_client.get("/control/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
