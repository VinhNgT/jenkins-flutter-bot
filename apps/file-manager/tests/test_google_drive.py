"""Unit tests for GoogleDriveBackend — token caching, save, and delete behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.oauth2.credentials import Credentials  # type: ignore

from file_manager.backends.google_drive import GoogleDriveBackend


@pytest.fixture
def token_path(tmp_path) -> Path:
    """Fixture for temporary token path."""
    return tmp_path / "token.json"


@pytest.fixture
def backend(token_path) -> GoogleDriveBackend:
    """Fixture for a GoogleDriveBackend with test credentials."""
    return GoogleDriveBackend(
        token_path,
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        folder_name="Test Builds",
    )


@pytest.fixture
def mock_credentials() -> MagicMock:
    """Fixture for valid mocked Google OAuth Credentials."""
    creds = MagicMock(spec=Credentials)
    creds.valid = True
    creds.token = "fake-token"
    creds.refresh_token = "fake-refresh-token"
    creds.token_uri = "https://oauth2.googleapis.com/token"
    creds.client_id = "fake-client-id"
    creds.client_secret = "fake-client-secret"
    creds.scopes = ["scope1"]
    return creds


class TestGoogleDriveBackendCaching:
    @pytest.mark.asyncio
    async def test_load_tokens_hits_disk_first_time(self, backend, mock_credentials):
        """First load_tokens call should offload to disk/thread and cache credentials."""
        assert backend._cached_creds is None

        with patch.object(backend, "_load_tokens_sync", return_value=mock_credentials) as mock_sync:
            creds = await backend.load_tokens()
            assert creds is mock_credentials
            assert backend._cached_creds is mock_credentials
            mock_sync.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_load_tokens_uses_cache_on_subsequent_calls(self, backend, mock_credentials):
        """Subsequent load_tokens calls should return cached credentials without disk offload."""
        backend._cached_creds = mock_credentials

        with patch.object(backend, "_load_tokens_sync") as mock_sync:
            creds = await backend.load_tokens()
            assert creds is mock_credentials
            mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_tokens_reloads_if_cache_invalid(self, backend, mock_credentials):
        """If cached credentials are valid=False, reload from disk/thread."""
        # Inject an invalid credential into the cache
        invalid_creds = MagicMock(spec=Credentials)
        invalid_creds.valid = False
        backend._cached_creds = invalid_creds

        with patch.object(backend, "_load_tokens_sync", return_value=mock_credentials) as mock_sync:
            creds = await backend.load_tokens()
            assert creds is mock_credentials
            assert backend._cached_creds is mock_credentials
            mock_sync.assert_called_once_with()

    def test_save_credentials_updates_cache(self, backend, mock_credentials):
        """Saving credentials updates the in-memory cache immediately."""
        assert backend._cached_creds is None

        # Verify saving also writes to disk by checking directory creation & saving
        with patch("file_manager.backends.google_drive.Path.write_text") as mock_write:
            backend._save_credentials(mock_credentials)
            assert backend._cached_creds is mock_credentials
            mock_write.assert_called_once()

    def test_delete_tokens_clears_cache(self, backend, mock_credentials):
        """Deleting tokens unlinks the file and clears the in-memory cache."""
        backend._cached_creds = mock_credentials

        # Write dummy file so deletion returns True
        backend.token_path.parent.mkdir(parents=True, exist_ok=True)
        backend.token_path.write_text("{}")

        assert backend.token_path.exists() is True
        result = backend.delete_tokens()

        assert result is True
        assert backend._cached_creds is None
        assert backend.token_path.exists() is False

    @pytest.mark.asyncio
    async def test_load_tokens_deletes_file_on_refresh_error(self, backend):
        """If refresh raises a RefreshError, the token file is deleted and cache cleared."""
        from google.auth.exceptions import RefreshError

        # Setup initial token file and cache
        backend.token_path.parent.mkdir(parents=True, exist_ok=True)
        backend.token_path.write_text('{"token": "fake-token", "refresh_token": "fake-refresh-token"}')

        # Mock credentials refresh to raise RefreshError
        with patch("file_manager.backends.google_drive.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = False
            mock_creds.refresh_token = "fake-refresh-token"
            mock_creds.refresh.side_effect = RefreshError("Token revoked")
            mock_creds_class.return_value = mock_creds

            creds = await backend.load_tokens()

            assert creds is None
            assert backend._cached_creds is None
            assert backend.token_path.exists() is False

    @pytest.mark.asyncio
    async def test_upload_deletes_tokens_on_refresh_error(self, backend):
        """If upload raises RefreshError, delete tokens and raise RuntimeError."""
        from google.auth.exceptions import RefreshError

        backend.token_path.parent.mkdir(parents=True, exist_ok=True)
        backend.token_path.write_text('{"token": "fake-token", "refresh_token": "fake-refresh-token"}')

        # Mock load_tokens to return a valid-looking credential, but _ensure_folder raises RefreshError
        valid_creds = MagicMock()
        with patch.object(backend, "load_tokens", return_value=valid_creds), \
             patch.object(backend, "_ensure_folder", side_effect=RefreshError("revoked")):

            with pytest.raises(RuntimeError, match="Google Drive credentials expired or revoked"):
                await backend.upload(b"data", "test.apk")

            assert backend.token_path.exists() is False
