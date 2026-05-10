"""Google Drive OAuth — wraps google-auth-oauthlib for both browser and headless flows."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveOAuth:
    """Manage the Google Drive OAuth flow and token persistence.

    Supports two exchange paths:
    - ``exchange_callback()`` — browser redirect (web dashboard)
    - ``exchange_code()``     — manual code paste (admin bot, headless)
    """

    def __init__(self, token_path: Path) -> None:
        self._token_path = token_path
        self._pending_flow: Flow | None = None

    @property
    def token_path(self) -> Path:
        return self._token_path

    # ----- internal -----

    @staticmethod
    def _allow_insecure_transport(redirect_uri: str) -> None:
        """Allow OAuth over plain HTTP when the redirect target isn't HTTPS.

        oauthlib rejects non-HTTPS redirect URIs by default.  In local /
        Docker development the callback is typically ``http://localhost:…``,
        so we need to opt out of that check.
        """
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

    # ----- public API -----

    def start(
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
        """Exchange the browser redirect callback for tokens and save them.

        This is the standard browser-redirect flow used by the web dashboard.
        The *authorization_response* is the full callback URL including
        the ``?code=`` query parameter.
        """
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
        """Exchange a manually-pasted auth code for tokens and save them.

        This is the headless flow used by the admin bot.  The user copies the
        ``code`` from the browser's redirect URL (after authorizing) and pastes
        it into the Telegram chat.
        """
        self._allow_insecure_transport("http://localhost")
        flow = Flow.from_client_config(
            self._client_config(client_id, client_secret, "http://localhost"),
            scopes=DRIVE_SCOPES,
        )
        flow.redirect_uri = "http://localhost"
        flow.fetch_token(code=code)
        self._save_credentials(flow.credentials)

    def load_tokens(
        self, client_id: str, client_secret: str
    ) -> Credentials | None:
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

    def status(self, client_id: str, client_secret: str) -> dict[str, Any]:
        """Return current OAuth connection status."""
        return {
            "connected": self.load_tokens(client_id, client_secret) is not None,
            "token_path": str(self._token_path),
        }

    def delete_tokens(self) -> bool:
        """Remove the saved OAuth token file.

        Returns ``True`` if the file was deleted, ``False`` if it didn't exist.
        """
        if not self._token_path.exists():
            return False
        self._token_path.unlink()
        logger.info("Removed Drive OAuth token at %s", self._token_path)
        return True
