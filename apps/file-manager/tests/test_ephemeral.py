"""Tests for the ephemeral local filesystem storage backend."""

from __future__ import annotations

from pathlib import Path
from file_manager.backends.ephemeral import EphemeralBackend


class TestEphemeralBackend:
    """Tests for EphemeralBackend upload/delete/status filesystem lifecycle."""

    async def test_upload_returns_result(self, tmp_path: Path) -> None:
        backend = EphemeralBackend(base_url="http://test:9092", data_dir=tmp_path)
        result = await backend.upload(b"hello world", "test.apk")
        assert result.file_id
        assert result.download_url.startswith("http://test:9092/api/files/")
        assert result.download_url.endswith("/download")

    async def test_upload_stores_data(self, tmp_path: Path) -> None:
        backend = EphemeralBackend(data_dir=tmp_path)
        result = await backend.upload(b"binary data", "app.apk")
        
        # Verify file exists on disk
        stored = backend.get(result.file_id)
        assert stored is not None
        assert stored.file_path.exists()
        assert stored.file_path.read_bytes() == b"binary data"
        assert stored.data == b"binary data"
        assert stored.filename == "app.apk"

    async def test_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        backend = EphemeralBackend(data_dir=tmp_path)
        assert backend.get("nonexistent") is None

    async def test_delete_removes_file(self, tmp_path: Path) -> None:
        backend = EphemeralBackend(data_dir=tmp_path)
        result = await backend.upload(b"data", "file.txt")
        stored = backend.get(result.file_id)
        assert stored is not None
        file_path = stored.file_path
        assert file_path.exists()

        await backend.delete(result.file_id)
        assert backend.get(result.file_id) is None
        assert not file_path.exists()

    async def test_delete_nonexistent_is_noop(self, tmp_path: Path) -> None:
        """Deleting a non-existent file should not raise."""
        backend = EphemeralBackend(data_dir=tmp_path)
        await backend.delete("does-not-exist")

    async def test_is_connected_always_true(self, tmp_path: Path) -> None:
        backend = EphemeralBackend(data_dir=tmp_path)
        assert await backend.is_connected() is True

    async def test_status_empty(self, tmp_path: Path) -> None:
        backend = EphemeralBackend(data_dir=tmp_path)
        status = await backend.status()
        assert status["backend"] == "ephemeral"
        assert status["connected"] is True
        assert status["file_count"] == 0
        assert status["total_size_bytes"] == 0

    async def test_status_reflects_uploads(self, tmp_path: Path) -> None:
        backend = EphemeralBackend(data_dir=tmp_path)
        await backend.upload(b"12345", "a.txt")
        await backend.upload(b"67890ab", "b.txt")
        status = await backend.status()
        assert status["file_count"] == 2
        assert status["total_size_bytes"] == 12  # 5 + 7

    async def test_multiple_uploads_get_unique_ids(self, tmp_path: Path) -> None:
        backend = EphemeralBackend(data_dir=tmp_path)
        r1 = await backend.upload(b"a", "a.txt")
        r2 = await backend.upload(b"b", "b.txt")
        assert r1.file_id != r2.file_id

    async def test_base_url_trailing_slash_stripped(self, tmp_path: Path) -> None:
        backend = EphemeralBackend(base_url="http://host:9092/", data_dir=tmp_path)
        result = await backend.upload(b"x", "x.txt")
        assert "http://host:9092/api/files/" in result.download_url
        assert "//" not in result.download_url.replace("http://", "")

    async def test_startup_wipe(self, tmp_path: Path) -> None:
        """Verify that files are completely wiped on startup."""
        backend1 = EphemeralBackend(data_dir=tmp_path)
        result = await backend1.upload(b"some data", "app.apk")
        stored = backend1.get(result.file_id)
        assert stored is not None
        file_path = stored.file_path
        assert file_path.exists()

        # Re-initialize should wipe the folder
        backend2 = EphemeralBackend(data_dir=tmp_path)
        assert not file_path.exists()
        assert backend2.get(result.file_id) is None

    async def test_graceful_shutdown_cleanup(self, tmp_path: Path) -> None:
        """Verify that cleanup() removes all files and directory."""
        backend = EphemeralBackend(data_dir=tmp_path)
        result = await backend.upload(b"some data", "app.apk")
        stored = backend.get(result.file_id)
        assert stored is not None
        file_path = stored.file_path
        assert file_path.exists()

        await backend.cleanup()
        assert not file_path.exists()
        assert not file_path.parent.exists()

