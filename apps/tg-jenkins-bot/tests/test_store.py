"""Unit tests for the ActiveBuildStore."""

from __future__ import annotations

import pytest
from tg_jenkins_bot.bot.store import ActiveBuildStore


def test_active_build_store_flow() -> None:
    """Test standard register, list, lookup, and consume flow."""
    clock_val = 1000.0
    store = ActiveBuildStore(clock=lambda: clock_val)

    # 1. Initially empty
    assert len(store.list_active()) == 0
    assert store.find_by_branch("main") is None

    # 2. Register a build
    build = store.register(
        request_id="req-123",
        chat_id=456,
        ref="main",
        label="Stable Release",
        triggered_by="Alice",
    )

    assert build.request_id == "req-123"
    assert build.chat_id == 456
    assert build.ref == "main"
    assert build.label == "Stable Release"
    assert build.triggered_at == 1000.0
    assert build.triggered_by == "Alice"

    # 3. Check list and lookup
    active = store.list_active()
    assert len(active) == 1
    assert active[0] == build

    assert store.find_by_branch("main") == build
    assert store.find_by_branch("develop") is None

    # 4. Consume the build
    consumed = store.consume("req-123")
    assert consumed == build

    # 5. Consume again yields None
    assert store.consume("req-123") is None
    assert len(store.list_active()) == 0
    assert store.find_by_branch("main") is None
