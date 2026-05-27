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
        stale, orphans = build_log.reconcile({"f2"})

        assert len(stale) == 1
        assert stale[0].request_id == "req1"
        assert orphans == set()
        assert len(build_log.recent()) == 1

    def test_detects_orphaned_files(self, build_log):
        """Drive files not tracked by any record are reported as orphans."""
        _record(build_log, "req1", file_id="f1")

        stale, orphans = build_log.reconcile({"f1", "f_orphan_1", "f_orphan_2"})

        assert stale == []
        assert orphans == {"f_orphan_1", "f_orphan_2"}
        assert len(build_log.recent()) == 1  # unchanged

    def test_mixed_stale_and_orphans(self, build_log):
        """Both stale records and orphaned files are handled in one call."""
        _record(build_log, "req1", file_id="f_gone")
        _record(build_log, "req2", file_id="f2")

        stale, orphans = build_log.reconcile({"f2", "f_orphan"})

        assert len(stale) == 1
        assert stale[0].file_id == "f_gone"
        assert orphans == {"f_orphan"}
        assert len(build_log.recent()) == 1

    def test_in_sync(self, build_log):
        """When everything matches, returns empty collections."""
        _record(build_log, "req1", file_id="f1")

        stale, orphans = build_log.reconcile({"f1"})

        assert stale == []
        assert orphans == set()

    def test_records_without_file_id_are_kept(self, build_log):
        """Failed build records (no file_id) survive reconciliation."""
        _record(build_log, "fail1", result="failure")  # no file_id
        _record(build_log, "req1", file_id="f1")

        stale, orphans = build_log.reconcile({"f1"})

        assert stale == []
        assert orphans == set()
        assert len(build_log.recent()) == 2

    def test_stale_records_persisted_to_disk(self, tmp_path):
        """Reconciliation saves the pruned log to disk."""
        log = BuildLog(data_dir=tmp_path, max_records=5, persistent=True)
        _record(log, "req1", file_id="f1")
        _record(log, "req2", file_id="f2")

        log.reconcile({"f2"})  # f1 is stale

        # Reload from disk
        log2 = BuildLog(data_dir=tmp_path, max_records=5, persistent=True)
        assert len(log2.recent()) == 1
        assert log2.recent()[0].request_id == "req2"

    def test_empty_drive_purges_all_file_records(self, build_log):
        """If Drive is empty, all records with file_ids are stale."""
        _record(build_log, "req1", file_id="f1")
        _record(build_log, "fail1", result="failure")

        stale, orphans = build_log.reconcile(set())

        assert len(stale) == 1
        assert stale[0].file_id == "f1"
        assert orphans == set()
        # The failure record (no file_id) survives
        assert len(build_log.recent()) == 1
