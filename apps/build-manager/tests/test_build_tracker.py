"""Tests for BuildTracker — pending builds, persistence, and edge cases."""

from __future__ import annotations

import json

import pytest
import time_machine

from build_manager.builds.state import BuildTracker, PendingBuild


@pytest.fixture
def tracker(tmp_path):
    """Create a fresh BuildTracker."""
    return BuildTracker(tmp_path)


@pytest.fixture
def tracker_factory(tmp_path):
    """Factory to create trackers sharing the same data directory."""
    def _make():
        return BuildTracker(tmp_path)
    return _make


# ---------------------------------------------------------------------------
# Pending builds
# ---------------------------------------------------------------------------


class TestPendingBuilds:
    def test_add_pending_persists_to_disk(self, tracker, tmp_path):
        tracker.add_pending("req1", "main", queue_id=10)
        data = json.loads((tmp_path / "pending_builds.json").read_text())
        assert "req1" in data
        assert data["req1"]["branch"] == "main"

    def test_add_pending_returns_pending_build(self, tracker):
        result = tracker.add_pending("req1", "main", queue_id=10)
        assert isinstance(result, PendingBuild)
        assert result.request_id == "req1"
        assert result.branch == "main"
        assert result.queue_id == 10

    def test_get_pending(self, tracker):
        tracker.add_pending("req1", "main")
        assert tracker.get_pending("req1") is not None
        assert tracker.get_pending("req1").branch == "main"

    def test_get_pending_unknown_returns_none(self, tracker):
        assert tracker.get_pending("nonexistent") is None

    def test_consume_pending_removes_and_persists(self, tracker, tmp_path):
        tracker.add_pending("req1", "main")
        result = tracker.consume_pending("req1")
        assert result is not None
        assert result.request_id == "req1"
        assert tracker.get_pending("req1") is None
        data = json.loads((tmp_path / "pending_builds.json").read_text())
        assert "req1" not in data

    def test_consume_pending_unknown_id_returns_none(self, tracker):
        assert tracker.consume_pending("nonexistent") is None

    def test_consume_pending_idempotent(self, tracker):
        """Second consume of same ID returns None."""
        tracker.add_pending("req1", "main")
        assert tracker.consume_pending("req1") is not None
        assert tracker.consume_pending("req1") is None

    def test_pending_count(self, tracker):
        assert tracker.pending_count == 0
        tracker.add_pending("a", "main")
        assert tracker.pending_count == 1
        tracker.add_pending("b", "dev")
        assert tracker.pending_count == 2

    def test_list_pending_returns_snapshot(self, tracker):
        tracker.add_pending("a", "main")
        tracker.add_pending("b", "dev")
        pending = tracker.list_pending()
        assert len(pending) == 2
        assert "a" in pending
        assert "b" in pending

    def test_frontend_callback_url_stored(self, tracker):
        tracker.add_pending("req1", "main", frontend_callback_url="http://bot:9090/callback")
        pending = tracker.get_pending("req1")
        assert pending.frontend_callback_url == "http://bot:9090/callback"


# ---------------------------------------------------------------------------
# Persistence across reload
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_stale_pending_cleared_on_reload(self, tracker_factory):
        """Pending builds from a previous process are cleared on startup."""
        t1 = tracker_factory()
        t1.add_pending("req1", "main", queue_id=10)
        # A new tracker instance simulates a process restart — stale
        # pending builds are cleared because no poll tasks exist for them.
        t2 = tracker_factory()
        assert t2.get_pending("req1") is None
        assert t2.pending_count == 0

    def test_corrupted_json_graceful_fallback(self, tmp_path):
        """Garbage JSON → empty state, no crash."""
        (tmp_path / "pending_builds.json").write_text("{invalid json!!!")
        tracker = BuildTracker(tmp_path)
        assert tracker.pending_count == 0


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


class TestMisc:
    def test_generate_request_id_uniqueness(self):
        ids = {BuildTracker.generate_request_id() for _ in range(1000)}
        assert len(ids) == 1000

    def test_generate_request_id_length(self):
        rid = BuildTracker.generate_request_id()
        assert len(rid) == 12

    def test_to_dict(self, tracker):
        tracker.add_pending("req1", "main")
        d = tracker.to_dict()
        assert d["pending_count"] == 1
        assert "req1" in d["pending"]

    @time_machine.travel(999.0, tick=False)
    def test_time_machine_controls_triggered_at(self, tmp_path):
        """Verify time-machine freezes time.time() used for triggered_at."""
        tracker = BuildTracker(tmp_path)
        pending = tracker.add_pending("req1", "main")
        assert pending.triggered_at == 999.0
