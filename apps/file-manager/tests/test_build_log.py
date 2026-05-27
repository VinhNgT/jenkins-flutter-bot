"""Tests for BuildLog — recording, retention, reconciliation."""

import pytest

from file_manager.build_log import BuildLog


@pytest.fixture
def build_log(tmp_path):
    """Create a persistent BuildLog with max 3 records."""
    return BuildLog(data_dir=tmp_path, max_records=3, persistent=True)


@pytest.fixture
def ephemeral_log(tmp_path):
    """Create an ephemeral (in-memory) BuildLog."""
    return BuildLog(data_dir=tmp_path, max_records=3, persistent=False)


def _record(log: BuildLog, request_id: str, *, file_id: str = "", result: str = "success"):
    """Helper to add a record with minimal boilerplate."""
    return log.record(
        request_id=request_id,
        branch="main",
        commit_hash="a" * 40,
        result=result,
        triggered_at=1.0,
        completed_at=2.0,
        file_id=file_id,
    )


# ---------------------------------------------------------------------------
# Recording & retention
# ---------------------------------------------------------------------------


class TestRecording:
    def test_record_appends(self, build_log):
        _record(build_log, "req1", file_id="f1")
        assert len(build_log.recent()) == 1
        assert build_log.recent()[0].request_id == "req1"

    def test_retention_evicts_oldest(self, build_log):
        _record(build_log, "req1", file_id="f1")
        _record(build_log, "req2", file_id="f2")
        _record(build_log, "req3", file_id="f3")
        evicted = _record(build_log, "req4", file_id="f4")
        assert len(evicted) == 1
        assert evicted[0].request_id == "req1"
        assert len(build_log.recent()) == 3

    def test_recent_newest_first(self, build_log):
        _record(build_log, "req1")
        _record(build_log, "req2")
        recent = build_log.recent()
        assert recent[0].request_id == "req2"

    def test_recent_success_only(self, build_log):
        _record(build_log, "ok", result="success")
        _record(build_log, "fail", result="failure")
        assert len(build_log.recent(success_only=True)) == 1


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_disk_persistence(self, tmp_path):
        log1 = BuildLog(data_dir=tmp_path, max_records=3, persistent=True)
        _record(log1, "req1", file_id="f1")

        log2 = BuildLog(data_dir=tmp_path, max_records=3, persistent=True)
        assert len(log2.recent()) == 1
        assert log2.recent()[0].request_id == "req1"

    def test_ephemeral_no_disk(self, tmp_path):
        log = BuildLog(data_dir=tmp_path, max_records=3, persistent=False)
        _record(log, "req1")
        assert not (tmp_path / "build_log.json").exists()

    def test_corrupted_json(self, tmp_path):
        (tmp_path / "build_log.json").write_text("{bad json!")
        log = BuildLog(data_dir=tmp_path, max_records=3, persistent=True)
        assert len(log.recent()) == 0


# ---------------------------------------------------------------------------
# remove_by_file_id
# ---------------------------------------------------------------------------


class TestRemoveByFileId:
    def test_removes_matching(self, build_log):
        _record(build_log, "req1", file_id="f1")
        _record(build_log, "req2", file_id="f2")
        build_log.remove_by_file_id("f1")
        assert len(build_log.recent()) == 1
        assert build_log.recent()[0].request_id == "req2"

    def test_no_match_is_noop(self, build_log):
        _record(build_log, "req1", file_id="f1")
        build_log.remove_by_file_id("nonexistent")
        assert len(build_log.recent()) == 1


# ---------------------------------------------------------------------------
# file_ids property
# ---------------------------------------------------------------------------


class TestFileIds:
    def test_returns_set_of_file_ids(self, build_log):
        _record(build_log, "req1", file_id="f1")
        _record(build_log, "req2", file_id="f2")
        _record(build_log, "req3")  # no file_id
        assert build_log.file_ids == {"f1", "f2"}

    def test_empty_log(self, build_log):
        assert build_log.file_ids == set()


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


class TestReconcile:
    def test_removes_stale_records(self, build_log):
        """Records pointing to missing Drive files are removed."""
        _record(build_log, "req1", file_id="f1")
        _record(build_log, "req2", file_id="f2")

        # f1 no longer exists in Drive
        stale, evicted = build_log.reconcile([{"id": "f2", "name": "f2.apk"}])

        assert len(stale) == 1
        assert stale[0].request_id == "req1"
        assert evicted == []
        assert len(build_log.recent()) == 1

    def test_recovers_orphaned_files(self, build_log):
        """Drive files not tracked by any record are recovered as synthetic records."""
        _record(build_log, "req1", file_id="f1")

        stale, evicted = build_log.reconcile([
            {"id": "f1", "name": "f1.apk"},
            {"id": "f_orphan_1", "name": "app-release.apk"},
        ])

        assert stale == []
        assert evicted == []
        recent = build_log.recent()
        assert len(recent) == 2
        # It's sorted by completed_at, let's just find it
        recovered = next(r for r in recent if r.file_id == "f_orphan_1")
        assert recovered.request_id == "recovered-f_orphan_1"
        assert recovered.branch == "app-release.apk"
        assert recovered.result == "success"
        assert "view?usp=sharing" in recovered.download_url

    def test_parses_created_time(self, build_log):
        """Recovers orphan and correctly parses its createdTime."""
        stale, evicted = build_log.reconcile([
            {"id": "f1", "name": "f1.apk", "createdTime": "2026-05-27T01:23:45.000Z"}
        ])

        assert stale == []
        assert evicted == []
        recent = build_log.recent()
        assert len(recent) == 1
        assert recent[0].completed_at > 0

    def test_evicts_excess_records(self, build_log):
        """If recovering orphans exceeds max_records, the oldest are evicted."""
        # max_records is 3
        _record(build_log, "req1", file_id="f1")  # completed_at 2.0
        
        stale, evicted = build_log.reconcile([
            {"id": "f1", "name": "f1.apk"},
            {"id": "f_orphan_1", "createdTime": "2026-05-27T10:00:00.000Z"},
            {"id": "f_orphan_2", "createdTime": "2026-05-27T11:00:00.000Z"},
            {"id": "f_orphan_3", "createdTime": "2026-05-27T12:00:00.000Z"},
        ])

        assert stale == []
        # Total records = 1 kept + 3 recovered = 4. Max = 3. One must be evicted.
        # req1 has completed_at=2.0 (1970-01-01), so it's the oldest!
        assert len(evicted) == 1
        assert evicted[0].request_id == "req1"
        assert len(build_log.recent()) == 3

    def test_mixed_stale_and_recovery(self, build_log):
        """Both stale records and recovered files handled in one call."""
        _record(build_log, "req1", file_id="f_gone")
        _record(build_log, "req2", file_id="f2")

        stale, evicted = build_log.reconcile([
            {"id": "f2", "name": "f2.apk"},
            {"id": "f_orphan", "name": "orphan.apk"},
        ])

        assert len(stale) == 1
        assert stale[0].file_id == "f_gone"
        assert evicted == []
        assert len(build_log.recent()) == 2

    def test_records_without_file_id_are_kept(self, build_log):
        """Failed build records (no file_id) survive reconciliation."""
        _record(build_log, "fail1", result="failure")  # no file_id
        _record(build_log, "req1", file_id="f1")

        stale, evicted = build_log.reconcile([{"id": "f1", "name": "f1.apk"}])

        assert stale == []
        assert evicted == []
        assert len(build_log.recent()) == 2

    def test_stale_records_persisted_to_disk(self, tmp_path):
        """Reconciliation saves the pruned log to disk."""
        log = BuildLog(data_dir=tmp_path, max_records=5, persistent=True)
        _record(log, "req1", file_id="f1")
        _record(log, "req2", file_id="f2")

        log.reconcile([{"id": "f2", "name": "f2.apk"}])  # f1 is stale

        # Reload from disk
        log2 = BuildLog(data_dir=tmp_path, max_records=5, persistent=True)
        assert len(log2.recent()) == 1
        assert log2.recent()[0].request_id == "req2"

    def test_empty_drive_purges_all_file_records(self, build_log):
        """If Drive is empty, all records with file_ids are stale."""
        _record(build_log, "req1", file_id="f1")
        _record(build_log, "fail1", result="failure")

        stale, evicted = build_log.reconcile([])

        assert len(stale) == 1
        assert stale[0].file_id == "f1"
        assert evicted == []
        # The failure record (no file_id) survives
        assert len(build_log.recent()) == 1
