"""Google Drive integration — token loading and file upload/management."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build as build_service
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveUploader:
    """Handles Google Drive file operations using OAuth tokens from config-ui.

    OAuth tokens are managed by config-ui and saved to a shared volume.
    This class only reads and refreshes those tokens — it never initiates
    the OAuth flow itself.

    All Drive API calls are offloaded to threads via asyncio.to_thread()
    to avoid blocking the event loop.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_path: Path,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_path = token_path
        self._folder_id_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def load_tokens(self) -> Credentials | None:
        """Load saved OAuth tokens from disk, refreshing if needed."""
        if not self._token_path.exists():
            return None

        data = json.loads(self._token_path.read_text())
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id", self._client_id),
            client_secret=data.get("client_secret", self._client_secret),
            scopes=data.get("scopes"),
        )

        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
            # Persist the refreshed access token
            data["token"] = creds.token
            self._token_path.write_text(json.dumps(data))

        return creds if creds.valid else None

    def is_connected(self) -> bool:
        """Check if Google Drive is connected (valid tokens exist)."""
        return self.load_tokens() is not None

    # ------------------------------------------------------------------
    # Drive file operations (sync internals wrapped with to_thread)
    # ------------------------------------------------------------------

    def _get_drive_service(self, creds: Credentials) -> Any:
        """Build an authenticated Drive API service."""
        return build_service("drive", "v3", credentials=creds)

    def _ensure_folder_sync(self, creds: Credentials, folder_name: str) -> str:
        """Find or create a Drive folder by name. Returns folder ID."""
        service = self._get_drive_service(creds)

        query = (
            f"name = '{folder_name}' and "
            f"mimeType = 'application/vnd.google-apps.folder' and "
            f"trashed = false"
        )
        results = (
            service.files()
            .list(q=query, spaces="drive", fields="files(id, name)")
            .execute()
        )
        files = results.get("files", [])

        if files:
            folder_id = files[0]["id"]
            logger.info(
                "Found existing Drive folder '%s' (ID: %s)",
                folder_name,
                folder_id,
            )
        else:
            file_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            folder = service.files().create(body=file_metadata, fields="id").execute()
            folder_id = folder["id"]
            logger.info(
                "Created Drive folder '%s' (ID: %s)",
                folder_name,
                folder_id,
            )

        return folder_id

    async def ensure_folder(self, creds: Credentials, folder_name: str) -> str:
        """Find or create a Drive folder by name. Returns folder ID."""
        if folder_name in self._folder_id_cache:
            return self._folder_id_cache[folder_name]

        folder_id = await asyncio.to_thread(
            self._ensure_folder_sync, creds, folder_name
        )
        self._folder_id_cache[folder_name] = folder_id
        return folder_id

    def _upload_file_sync(
        self,
        file_path: str,
        filename: str,
        creds: Credentials,
        folder_id: str,
    ) -> tuple[str, str]:
        """Upload a file to Google Drive (blocking).

        Returns (file_id, web_view_link).
        """
        service = self._get_drive_service(creds)

        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(
            file_path,
            mimetype="application/vnd.android.package-archive",
            resumable=True,
        )

        logger.info("Uploading %s to Drive folder %s", filename, folder_id)

        file = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
            )
            .execute()
        )

        file_id = file["id"]

        # Make file viewable by anyone with the link
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        # Re-fetch to get the updated link
        file = service.files().get(fileId=file_id, fields="webViewLink").execute()
        web_link = file.get("webViewLink", "")

        logger.info("Uploaded: %s -> %s", filename, web_link)
        return file_id, web_link

    async def upload_file(
        self,
        file_path: str,
        filename: str,
        creds: Credentials,
        folder_id: str,
    ) -> tuple[str, str]:
        """Upload a file to Google Drive.

        Returns (file_id, web_view_link).
        """
        return await asyncio.to_thread(
            self._upload_file_sync, file_path, filename, creds, folder_id
        )

    def _delete_file_sync(self, creds: Credentials, file_id: str) -> None:
        """Delete a file from Google Drive (blocking)."""
        service = self._get_drive_service(creds)
        service.files().delete(fileId=file_id).execute()
        logger.info("Deleted Drive file: %s", file_id)

    async def delete_file(self, creds: Credentials, file_id: str) -> None:
        """Delete a file from Google Drive."""
        await asyncio.to_thread(self._delete_file_sync, creds, file_id)
