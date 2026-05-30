"""Tests for the log-only storage backend."""

from __future__ import annotations

from file_manager.backends.log_only import LogOnlyBackend


class TestLogOnlyBackend:
    """Tests for LogOnlyBackend — verifies the protocol contract is met."""

    async def test_upload_returns_valid_result(self) -> None:
        backend = LogOnlyBackend()
        result = await backend.upload(b"file content", "app-release.apk")
        assert result.file_id
        assert result.download_url.startswith("log-only://")
        assert "app-release.apk" in result.download_url

    async def test_upload_generates_unique_ids(self) -> None:
        backend = LogOnlyBackend()
        r1 = await backend.upload(b"a", "a.apk")
        r2 = await backend.upload(b"b", "b.apk")
        assert r1.file_id != r2.file_id

    async def test_delete_does_not_raise(self) -> None:
        """Delete is a no-op but must not raise."""
        backend = LogOnlyBackend()
        await backend.delete("any-file-id")

    async def test_is_connected_always_true(self) -> None:
        backend = LogOnlyBackend()
        assert await backend.is_connected() is True

    async def test_status_returns_correct_shape(self) -> None:
        backend = LogOnlyBackend()
        status = await backend.status()
        assert status["backend"] == "log_only"
        assert status["connected"] is True
        assert status["configured"] is True

    async def test_upload_empty_data(self) -> None:
        """Zero-byte uploads should work (edge case for log-only)."""
        backend = LogOnlyBackend()
        result = await backend.upload(b"", "empty.apk")
        assert result.file_id
        assert result.download_url
