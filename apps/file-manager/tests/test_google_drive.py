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
    async def test_load_tokens_hits_disk_first_time(self, token_path, mock_credentials):
        """First load_tokens call should offload to disk/thread and cache credentials."""
        backend = GoogleDriveBackend(token_path)
        assert backend._cached_creds is None

        with patch.object(backend, "_load_tokens_sync", return_value=mock_credentials) as mock_sync:
            creds = await backend.load_tokens("cid", "csecret")
            assert creds is mock_credentials
            assert backend._cached_creds is mock_credentials
            mock_sync.assert_called_once_with("cid", "csecret")

    @pytest.mark.asyncio
    async def test_load_tokens_uses_cache_on_subsequent_calls(self, token_path, mock_credentials):
        """Subsequent load_tokens calls should return cached credentials without disk offload."""
        backend = GoogleDriveBackend(token_path)
        backend._cached_creds = mock_credentials

        with patch.object(backend, "_load_tokens_sync") as mock_sync:
            creds = await backend.load_tokens("cid", "csecret")
            assert creds is mock_credentials
            mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_tokens_reloads_if_cache_invalid(self, token_path, mock_credentials):
        """If cached credentials are valid=False, reload from disk/thread."""
        backend = GoogleDriveBackend(token_path)
        
        # Inject an invalid credential into the cache
        invalid_creds = MagicMock(spec=Credentials)
        invalid_creds.valid = False
        backend._cached_creds = invalid_creds

        with patch.object(backend, "_load_tokens_sync", return_value=mock_credentials) as mock_sync:
            creds = await backend.load_tokens("cid", "csecret")
            assert creds is mock_credentials
            assert backend._cached_creds is mock_credentials
            mock_sync.assert_called_once_with("cid", "csecret")

    def test_save_credentials_updates_cache(self, token_path, mock_credentials):
        """Saving credentials updates the in-memory cache immediately."""
        backend = GoogleDriveBackend(token_path)
        assert backend._cached_creds is None

        # Verify saving also writes to disk by checking directory creation & saving
        with patch("file_manager.backends.google_drive.Path.write_text") as mock_write:
            backend._save_credentials(mock_credentials)
            assert backend._cached_creds is mock_credentials
            mock_write.assert_called_once()

    def test_delete_tokens_clears_cache(self, token_path, mock_credentials):
        """Deleting tokens unlinks the file and clears the in-memory cache."""
        backend = GoogleDriveBackend(token_path)
        backend._cached_creds = mock_credentials

        # Write dummy file so deletion returns True
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text("{}")

        assert token_path.exists() is True
        result = backend.delete_tokens()

        assert result is True
        assert backend._cached_creds is None
        assert token_path.exists() is False
