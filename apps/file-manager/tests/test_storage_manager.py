"""Tests for StorageManager — lifecycle, config validation, backend routing."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from file_manager.backends.ephemeral import EphemeralBackend
from file_manager.backends.google_drive import GoogleDriveBackend
from file_manager.backends.log_only import LogOnlyBackend
from file_manager.manager import StorageManager
from file_manager.storage import StorageBackend, UploadResult


@pytest.fixture(autouse=True)
def isolate_config(tmp_path):
    os.environ["JFB_DATA_DIR"] = str(tmp_path)
    yield tmp_path
    os.environ.pop("JFB_DATA_DIR", None)
    os.environ.pop("STORAGE_BACKEND", None)


@pytest.fixture
def mock_backend():
    """A mock that satisfies the StorageBackend protocol."""
    backend = MagicMock(spec=StorageBackend)
    backend.upload = AsyncMock(return_value=UploadResult("id1", "http://url"))
    backend.delete = AsyncMock()
    backend.is_connected = AsyncMock(return_value=True)
    backend.status = AsyncMock(return_value={"connected": True})
    return backend


# ---------------------------------------------------------------------------
# start / stop / restart
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_start_with_injected_backend(self, mock_backend, isolate_config):
        """With injected backend, starts without creating a real backend."""
        import json

        config_path = isolate_config / "storage.json"
        config_path.write_text(json.dumps({
            "drive": {"client_id": "cid", "client_secret": "csecret"},
        }))

        mgr = StorageManager(backend=mock_backend)
        await mgr.start()
        assert mgr.running is True
        assert mgr.backend is mock_backend

    async def test_start_ephemeral_mode(self, isolate_config):
        """With STORAGE_BACKEND=ephemeral, creates an EphemeralBackend."""
        os.environ["STORAGE_BACKEND"] = "ephemeral"

        mgr = StorageManager()
        await mgr.start()
        assert mgr.running is True
        assert isinstance(mgr.backend, EphemeralBackend)
        assert mgr.backend_type == "ephemeral"

    async def test_start_log_only_mode(self, isolate_config):
        """With STORAGE_BACKEND=log_only, creates a LogOnlyBackend."""
        os.environ["STORAGE_BACKEND"] = "log_only"

        mgr = StorageManager()
        await mgr.start()
        assert mgr.running is True
        assert isinstance(mgr.backend, LogOnlyBackend)
        assert mgr.backend_type == "log_only"

    async def test_start_google_drive_mode(self, isolate_config):
        """With STORAGE_BACKEND=google_drive, creates a GoogleDriveBackend."""
        import json

        config_path = isolate_config / "storage.json"
        config_path.write_text(json.dumps({
            "drive": {"client_id": "cid", "client_secret": "csecret"},
        }))

        os.environ["STORAGE_BACKEND"] = "google_drive"

        mgr = StorageManager()
        await mgr.start()
        assert mgr.running is True
        assert isinstance(mgr.backend, GoogleDriveBackend)
        assert mgr.backend_type == "google_drive"

    async def test_stop_clears_state(self, mock_backend, isolate_config):
        import json

        config_path = isolate_config / "storage.json"
        config_path.write_text(json.dumps({
            "drive": {"client_id": "cid", "client_secret": "csecret"},
        }))

        mgr = StorageManager(backend=mock_backend)
        await mgr.start()
        assert mgr.running is True

        await mgr.stop()
        assert mgr.running is False
        assert mgr.config is None


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_not_running(self, isolate_config):
        mgr = StorageManager()
        status = mgr.status()
        assert status["running"] is False
        assert "backend_type" in status

    async def test_status_running(self, mock_backend, isolate_config):
        import json

        config_path = isolate_config / "storage.json"
        config_path.write_text(json.dumps({
            "drive": {"client_id": "cid", "client_secret": "csecret"},
        }))

        mgr = StorageManager(backend=mock_backend)
        await mgr.start()
        status = mgr.status()
        assert status["running"] is True
        assert "started_at" in status
        assert "backend_type" in status

    def test_status_ephemeral_backend_type(self, isolate_config):
        """Status reports ephemeral backend type when configured."""
        os.environ["STORAGE_BACKEND"] = "ephemeral"
        mgr = StorageManager()
        status = mgr.status()
        assert status["backend_type"] == "ephemeral"

    def test_status_log_only_backend_type(self, isolate_config):
        """Status reports log_only backend type when configured."""
        os.environ["STORAGE_BACKEND"] = "log_only"
        mgr = StorageManager()
        status = mgr.status()
        assert status["backend_type"] == "log_only"


# ---------------------------------------------------------------------------
# backend accessors
# ---------------------------------------------------------------------------


class TestBackendAccessors:
    async def test_google_drive_backend_accessor(self, isolate_config):
        """google_drive_backend returns backend when using Drive."""
        import json

        config_path = isolate_config / "storage.json"
        config_path.write_text(json.dumps({
            "drive": {"client_id": "cid", "client_secret": "csecret"},
        }))
        os.environ["STORAGE_BACKEND"] = "google_drive"

        mgr = StorageManager()
        await mgr.start()
        assert mgr.google_drive_backend is not None
        assert mgr.ephemeral_backend is None

    async def test_ephemeral_backend_accessor(self, isolate_config):
        """ephemeral_backend returns backend when using ephemeral."""
        os.environ["STORAGE_BACKEND"] = "ephemeral"

        mgr = StorageManager()
        await mgr.start()
        assert mgr.ephemeral_backend is not None
        assert mgr.google_drive_backend is None
