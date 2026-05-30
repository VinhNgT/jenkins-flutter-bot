"""Tests for the ephemeral in-memory storage backend."""

from __future__ import annotations

from file_manager.backends.ephemeral import EphemeralBackend


class TestEphemeralBackend:
    """Tests for EphemeralBackend upload/delete/status lifecycle."""

    async def test_upload_returns_result(self) -> None:
        backend = EphemeralBackend(base_url="http://test:9092")
        result = await backend.upload(b"hello world", "test.apk")
        assert result.file_id
        assert result.download_url.startswith("http://test:9092/api/files/")
        assert result.download_url.endswith("/download")

    async def test_upload_stores_data(self) -> None:
        backend = EphemeralBackend()
        result = await backend.upload(b"binary data", "app.apk")
        stored = backend.get(result.file_id)
        assert stored is not None
        assert stored.data == b"binary data"
        assert stored.filename == "app.apk"

    async def test_get_nonexistent_returns_none(self) -> None:
        backend = EphemeralBackend()
        assert backend.get("nonexistent") is None

    async def test_delete_removes_file(self) -> None:
        backend = EphemeralBackend()
        result = await backend.upload(b"data", "file.txt")
        await backend.delete(result.file_id)
        assert backend.get(result.file_id) is None

    async def test_delete_nonexistent_is_noop(self) -> None:
        """Deleting a non-existent file should not raise."""
        backend = EphemeralBackend()
        await backend.delete("does-not-exist")

    async def test_is_connected_always_true(self) -> None:
        backend = EphemeralBackend()
        assert await backend.is_connected() is True

    async def test_status_empty(self) -> None:
        backend = EphemeralBackend()
        status = await backend.status()
        assert status["backend"] == "ephemeral"
        assert status["connected"] is True
        assert status["file_count"] == 0
        assert status["total_size_bytes"] == 0

    async def test_status_reflects_uploads(self) -> None:
        backend = EphemeralBackend()
        await backend.upload(b"12345", "a.txt")
        await backend.upload(b"67890ab", "b.txt")
        status = await backend.status()
        assert status["file_count"] == 2
        assert status["total_size_bytes"] == 12  # 5 + 7

    async def test_multiple_uploads_get_unique_ids(self) -> None:
        backend = EphemeralBackend()
        r1 = await backend.upload(b"a", "a.txt")
        r2 = await backend.upload(b"b", "b.txt")
        assert r1.file_id != r2.file_id

    async def test_base_url_trailing_slash_stripped(self) -> None:
        backend = EphemeralBackend(base_url="http://host:9092/")
        result = await backend.upload(b"x", "x.txt")
        assert "http://host:9092/api/files/" in result.download_url
        assert "//" not in result.download_url.replace("http://", "")
