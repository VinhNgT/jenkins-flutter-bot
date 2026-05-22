"""Tests for BuildTracker — persistence, retention, and edge cases."""

import json

import pytest

from build_manager.builds.state import BuildTracker, PendingBuild, CompletedBuild


@pytest.fixture
def tracker(tmp_path):
    """Create a fresh BuildTracker with max_recent_builds=3."""
    return BuildTracker(tmp_path, max_recent_builds=3, clock=lambda: 1_700_000_000.0)


@pytest.fixture
def tracker_factory(tmp_path):
    """Factory to create trackers sharing the same data directory."""
    def _make(clock=None):
        return BuildTracker(
            tmp_path,
            max_recent_builds=3,
            clock=clock or (lambda: 1_700_000_000.0),
        )
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

    def test_is_queue_full_boundary(self, tracker):
        """Queue full exactly at max_recent_builds."""
        tracker.add_pending("a", "main")
        tracker.add_pending("b", "dev")
        assert not tracker.is_queue_full
        tracker.add_pending("c", "staging")
        assert tracker.is_queue_full  # 3 == max

    def test_frontend_callback_url_stored(self, tracker):
        tracker.add_pending("req1", "main", frontend_callback_url="http://bot:9090/callback")
        pending = tracker.get_pending("req1")
        assert pending.frontend_callback_url == "http://bot:9090/callback"


# ---------------------------------------------------------------------------
# Completed builds
# ---------------------------------------------------------------------------


class TestCompletedBuilds:
    def test_record_completed(self, tracker):
        completed, evicted = tracker.record_completed(
            "req1",
            branch="main",
            commit_hash="a" * 40,
            result="success",
            triggered_at=1_700_000_000.0,
            completed_at=1_700_000_060.0,
            download_url="https://example.com/build.apk",
            file_id="file123",
        )
        assert isinstance(completed, CompletedBuild)
        assert completed.result == "success"
        assert evicted == []

    def test_record_completed_evicts_oldest(self, tracker):
        """When exceeding max, oldest builds are evicted."""
        for i in range(3):
            tracker.record_completed(
                f"req{i}",
                branch="main",
                commit_hash="a" * 40,
                result="success",
                triggered_at=1_700_000_000.0 + i,
                completed_at=1_700_000_060.0 + i,
            )
        # 4th build should evict the 1st
        _, evicted = tracker.record_completed(
            "req3",
            branch="main",
            commit_hash="b" * 40,
            result="success",
            triggered_at=1_700_000_003.0,
            completed_at=1_700_000_063.0,
        )
        assert len(evicted) == 1
        assert evicted[0].request_id == "req0"

    def test_recent_builds_newest_first(self, tracker):
        for i in range(3):
            tracker.record_completed(
                f"req{i}",
                branch="main",
                commit_hash="a" * 40,
                result="success",
                triggered_at=float(i),
                completed_at=float(i + 60),
            )
        recent = tracker.recent_builds(count=10)
        assert recent[0].request_id == "req2"
        assert recent[-1].request_id == "req0"

    def test_recent_builds_success_only_filter(self, tracker):
        tracker.record_completed(
            "ok", branch="main", commit_hash="a" * 40, result="success",
            triggered_at=1.0, completed_at=2.0,
        )
        tracker.record_completed(
            "fail", branch="main", commit_hash="b" * 40, result="failure",
            triggered_at=3.0, completed_at=4.0,
        )
        successful = tracker.recent_builds(count=10, success_only=True)
        assert len(successful) == 1
        assert successful[0].request_id == "ok"

    def test_recent_builds_count_limit(self, tracker, tmp_path):
        t = BuildTracker(tmp_path, max_recent_builds=10)
        for i in range(5):
            t.record_completed(
                f"req{i}", branch="main", commit_hash="a" * 40,
                result="success", triggered_at=float(i), completed_at=float(i + 60),
            )
        assert len(t.recent_builds(count=2)) == 2


# ---------------------------------------------------------------------------
# Persistence across reload
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_pending_survives_reload(self, tracker_factory):
        t1 = tracker_factory()
        t1.add_pending("req1", "main", queue_id=10)
        # Create new tracker from same directory
        t2 = tracker_factory()
        assert t2.get_pending("req1") is not None
        assert t2.get_pending("req1").branch == "main"

    def test_completed_survives_reload(self, tracker_factory):
        t1 = tracker_factory()
        t1.record_completed(
            "req1", branch="main", commit_hash="a" * 40,
            result="success", triggered_at=1.0, completed_at=2.0,
        )
        t2 = tracker_factory()
        recent = t2.recent_builds()
        assert len(recent) == 1
        assert recent[0].request_id == "req1"

    def test_corrupted_json_graceful_fallback(self, tmp_path):
        """Garbage JSON → empty state, no crash."""
        (tmp_path / "pending_builds.json").write_text("{invalid json!!!")
        (tmp_path / "completed_builds.json").write_text("not json")
        tracker = BuildTracker(tmp_path)
        assert tracker.pending_count == 0
        assert tracker.recent_builds() == []


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
        assert d["completed_count"] == 0
        assert "req1" in d["pending"]

    def test_clock_injection(self, tmp_path):
        """Verify the injected clock is used for triggered_at."""
        clock = lambda: 999.0  # noqa: E731
        tracker = BuildTracker(tmp_path, clock=clock)
        pending = tracker.add_pending("req1", "main")
        assert pending.triggered_at == 999.0
