"""Shared test fixtures and domain-object factories.

Provides reusable factory functions for creating domain objects with
sensible defaults, and a ``mock_http_client`` fixture for injecting
``httpx.MockTransport``-backed clients into any service adapter.

Factories are plain functions (not fixtures) so tests can call them
inline with overrides:  ``pending_build_factory(branch="dev")``.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest


# ── Domain Object Factories ─────────────────────────────────────────


def pending_build_factory(**overrides: Any) -> Any:
    """Create a ``PendingBuild`` with sensible defaults."""
    from build_manager.builds.state import PendingBuild

    defaults: dict[str, Any] = {
        "request_id": "abc123def456",
        "branch": "main",
        "triggered_at": 1_700_000_000.0,
        "queue_id": 1,
        "frontend_callback_url": "",
    }
    defaults.update(overrides)
    return PendingBuild(**defaults)


def completed_build_factory(**overrides: Any) -> Any:
    """Create a ``CompletedBuild`` with sensible defaults."""
    from build_manager.builds.state import CompletedBuild

    defaults: dict[str, Any] = {
        "request_id": "abc123def456",
        "branch": "main",
        "commit_hash": "a" * 40,
        "result": "success",
        "triggered_at": 1_700_000_000.0,
        "completed_at": 1_700_000_120.0,
        "download_url": "https://example.com/build.apk",
        "file_id": "drive_file_id_123",
    }
    defaults.update(overrides)
    return CompletedBuild(**defaults)


def jenkins_build_factory(**overrides: Any) -> Any:
    """Create a ``JenkinsBuild`` with sensible defaults."""
    from build_manager.builds.jenkins_client import JenkinsBuild

    defaults: dict[str, Any] = {
        "number": 42,
        "result": "SUCCESS",
        "building": False,
        "timestamp": 1_700_000_000.0,
        "duration_ms": 60_000,
        "branch": "main",
        "commit_hash": "a" * 40,
        "request_id": "abc123def456",
    }
    defaults.update(overrides)
    return JenkinsBuild(**defaults)


def tracked_message_factory(**overrides: Any) -> Any:
    """Create a ``TrackedMessage`` with sensible defaults."""
    from tg_jenkins_bot.bot.tracker import TrackedMessage

    defaults: dict[str, Any] = {
        "chat_id": 12345,
        "message_id": 100,
        "user_id": 67890,
        "state": "building",
        "created_at": 1_700_000_000.0,
        "data": {"ref": "main", "request_id": "abc123def456"},
    }
    defaults.update(overrides)
    return TrackedMessage(**defaults)


# ── HTTP Mock Fixtures ───────────────────────────────────────────────


@pytest.fixture
def mock_http_client():
    """Create an ``httpx.AsyncClient`` backed by ``MockTransport``.

    Usage::

        def my_handler(request):
            return httpx.Response(200, json={"ok": True})

        client = mock_http_client(my_handler)
    """
    clients: list[httpx.AsyncClient] = []

    def _factory(handler):  # noqa: ANN001
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        clients.append(client)
        return client

    yield _factory

    import asyncio

    for c in clients:
        try:
            asyncio.get_event_loop().run_until_complete(c.aclose())
        except Exception:
            pass
