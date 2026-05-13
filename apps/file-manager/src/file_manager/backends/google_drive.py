"""Google Drive storage backend.

Implements the ``StorageBackend`` protocol using Google Drive as the
storage provider.  Handles both OAuth token lifecycle and file
upload/delete operations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request  # type: ignore
from google.oauth2.credentials import Credentials  # type: ignore
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build as build_service
from googleapiclient.http import MediaFileUpload

from ..storage import UploadResult

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleDriveBackend:
    """Google Drive implementation of the ``StorageBackend`` protocol.

    Handles OAuth token lifecycle and file upload/delete operations.
    All Drive API calls are offloaded to threads via ``asyncio.to_thread()``
    to avoid blocking the event loop.
    """

    def __init__(self, token_path: Path) -> None:
        self._token_path = token_path
        self._pending_flow: Flow | None = None
        self._folder_id_cache: dict[str, str] = {}

    @property
    def token_path(self) -> Path:
        return self._token_path

    # ------------------------------------------------------------------
    # OAuth helpers (migrated from legacy drive module)
    # ------------------------------------------------------------------

    @staticmethod
    def _allow_insecure_transport(redirect_uri: str) -> None:
        """Allow OAuth over plain HTTP when the redirect target isn't HTTPS."""
        if redirect_uri.startswith("http://"):
            os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    def _client_config(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> dict[str, dict[str, Any]]:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

    def _build_flow(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> Flow:
        self._allow_insecure_transport(redirect_uri)
        flow = Flow.from_client_config(
            self._client_config(client_id, client_secret, redirect_uri),
            scopes=DRIVE_SCOPES,
        )
        flow.redirect_uri = redirect_uri
        return flow

    def _save_credentials(self, creds: Credentials) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(
            json.dumps(
                {
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": list(creds.scopes or []),
                }
            )
        )
        logger.info("Saved Drive OAuth tokens to %s", self._token_path)

    # ------------------------------------------------------------------
    # OAuth public API
    # ------------------------------------------------------------------

    def start_auth(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> str:
        """Generate the OAuth consent URL and store the flow for callback.

        Returns the authorization URL the user should open in a browser.
        """
        flow = self._build_flow(client_id, client_secret, redirect_uri)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
        )
        self._pending_flow = flow
        return auth_url

    def exchange_callback(self, authorization_response: str) -> None:
        """Exchange the browser redirect callback for tokens and save them."""
        flow = self._pending_flow
        if flow is None:
            raise RuntimeError(
                "No pending OAuth flow. Start authorization again from the dashboard."
            )
        self._pending_flow = None
        flow.fetch_token(authorization_response=authorization_response)
        self._save_credentials(flow.credentials)

    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        """Exchange a manually-pasted auth code for tokens and save them."""
        self._allow_insecure_transport("http://localhost")
        flow = Flow.from_client_config(
            self._client_config(client_id, client_secret, "http://localhost"),
            scopes=DRIVE_SCOPES,
        )
        flow.redirect_uri = "http://localhost"
        flow.fetch_token(code=code)
        self._save_credentials(flow.credentials)

    def load_tokens(self, client_id: str, client_secret: str) -> Credentials | None:
        """Load saved OAuth tokens from disk, refreshing if needed."""
        if not self._token_path.exists():
            return None

        data = json.loads(self._token_path.read_text())
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id", client_id),
            client_secret=data.get("client_secret", client_secret),
            scopes=data.get("scopes"),
        )

        if not creds.valid and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                logger.exception("Failed to refresh Drive token")
                return None

            data["token"] = creds.token
            self._token_path.write_text(json.dumps(data))

        return creds if creds.valid else None

    def delete_tokens(self) -> bool:
        """Remove the saved OAuth token file."""
        if not self._token_path.exists():
            return False
        self._token_path.unlink()
        logger.info("Removed Drive OAuth token at %s", self._token_path)
        return True

    # ------------------------------------------------------------------
    # Drive file operations (sync internals wrapped with to_thread)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_drive_service(creds: Credentials) -> Any:
        """Build an authenticated Drive API service."""
        return build_service("drive", "v3", credentials=creds)

    @staticmethod
    def _folder_link(folder_id: str) -> str:
        """Return the public Google Drive folder browse URL."""
        return f"https://drive.google.com/drive/folders/{folder_id}"

    def _ensure_folder_sync(self, creds: Credentials, folder_name: str) -> str:
        """Find or create a Drive folder by name. Returns folder_id."""
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

    async def _ensure_folder(self, creds: Credentials, folder_name: str) -> str:
        """Find or create a Drive folder by name. Returns folder_id."""
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
    ) -> UploadResult:
        """Upload a file to Google Drive (blocking). Returns UploadResult."""
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
                fields="id",
            )
            .execute()
        )

        file_id = file["id"]
        web_link = f"https://drive.google.com/uc?export=download&id={file_id}"

        # Grant public read access to this file only.
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            fields="id",
        ).execute()

        logger.info("Uploaded: %s -> %s", filename, web_link)
        return UploadResult(file_id=file_id, download_url=web_link)

    def _delete_file_sync(self, creds: Credentials, file_id: str) -> None:
        """Delete a file from Google Drive (blocking)."""
        service = self._get_drive_service(creds)
        service.files().delete(fileId=file_id).execute()
        logger.info("Deleted Drive file: %s", file_id)

    # ------------------------------------------------------------------
    # StorageBackend protocol implementation
    # ------------------------------------------------------------------

    async def upload(
        self,
        file_path: str,
        filename: str,
        *,
        folder_name: str = "",
        client_id: str = "",
        client_secret: str = "",
    ) -> UploadResult:
        """Upload a file to Google Drive.

        ``folder_name``, ``client_id``, and ``client_secret`` are passed
        by the ``StorageManager`` from the resolved config.
        """
        creds = self.load_tokens(client_id, client_secret)
        if creds is None:
            raise RuntimeError("Google Drive not connected — no valid tokens")

        folder_id = await self._ensure_folder(creds, folder_name)
        return await asyncio.to_thread(
            self._upload_file_sync, file_path, filename, creds, folder_id
        )

    async def delete(
        self,
        file_id: str,
        *,
        client_id: str = "",
        client_secret: str = "",
    ) -> None:
        """Delete a file from Google Drive."""
        creds = self.load_tokens(client_id, client_secret)
        if creds is None:
            raise RuntimeError("Google Drive not connected — no valid tokens")
        await asyncio.to_thread(self._delete_file_sync, creds, file_id)

    async def is_connected(
        self,
        *,
        client_id: str = "",
        client_secret: str = "",
    ) -> bool:
        """Return True if valid Drive tokens exist."""
        return self.load_tokens(client_id, client_secret) is not None

    def status(
        self,
        *,
        client_id: str = "",
        client_secret: str = "",
    ) -> dict[str, Any]:
        """Return current OAuth connection status."""
        return {
            "connected": self.load_tokens(client_id, client_secret) is not None,
            "token_path": str(self._token_path),
        }
