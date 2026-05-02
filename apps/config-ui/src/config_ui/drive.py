"""Google Drive OAuth helpers for config-ui."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveOAuthManager:
    """Own the config-ui side of the Google Drive OAuth flow."""

    def __init__(self, token_path: Path) -> None:
        self._token_path = token_path
        self._pending_flow: InstalledAppFlow | None = None

    @property
    def token_path(self) -> Path:
        return self._token_path

    @property
    def auth_pending(self) -> bool:
        return self._pending_flow is not None

    def _client_config(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> dict[str, dict[str, Any]]:
        return {
            "installed": {
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
    ) -> InstalledAppFlow:
        flow = InstalledAppFlow.from_client_config(
            self._client_config(client_id, client_secret, redirect_uri),
            scopes=SCOPES,
        )
        flow.redirect_uri = redirect_uri
        return flow

    def start(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> str:
        flow = self._build_flow(client_id, client_secret, redirect_uri)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
        )
        self._pending_flow = flow
        return auth_url

    def _consume_pending_flow(self) -> InstalledAppFlow:
        flow = self._pending_flow
        if flow is None:
            raise RuntimeError(
                "No pending OAuth flow. Start authorization again from the dashboard."
            )
        self._pending_flow = None
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

    def exchange_code(self, code: str) -> None:
        flow = self._consume_pending_flow()
        flow.fetch_token(code=code)
        self._save_credentials(flow.credentials)

    def exchange_callback(self, authorization_response: str) -> None:
        flow = self._consume_pending_flow()
        flow.fetch_token(authorization_response=authorization_response)
        self._save_credentials(flow.credentials)

    def load_tokens(self, client_id: str, client_secret: str) -> Credentials | None:
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
            except Exception as exc:
                logger.warning("Failed to refresh Drive token: %s", exc)
                return None

            data["token"] = creds.token
            self._token_path.write_text(json.dumps(data))

        return creds if creds.valid else None

    def status(self, client_id: str, client_secret: str) -> dict[str, Any]:
        return {
            "connected": self.load_tokens(client_id, client_secret) is not None,
            "auth_pending": self.auth_pending,
            "token_path": str(self._token_path),
        }
