"""Flat environment-based configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DATA_DIR = Path("data")
OAUTH_TOKEN_PATH = DATA_DIR / "oauth.json"


def _default_oauth_token_path(config_path: Path | None) -> Path:
    """Keep OAuth tokens next to the active config file when possible."""
    if config_path is not None:
        return config_path.parent / "oauth.json"
    return OAUTH_TOKEN_PATH


def _nested_get(data: dict[str, Any], dotted_key: str) -> Any:
    """Read a dotted key from nested dict data."""
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _parse_allowed_chat_ids(raw: Any) -> list[int]:
    """Normalize allowed chat IDs from JSON or env-style values."""
    if isinstance(raw, list):
        return [int(value) for value in raw]
    if isinstance(raw, str):
        return [int(value.strip()) for value in raw.split(",") if value.strip()]
    raise ValueError("ALLOWED_CHAT_IDS must be a list or CSV string")


@dataclass(frozen=True)
class Config:
    """Bot configuration resolved from config file, env, and defaults."""

    # Telegram
    telegram_token: str
    allowed_chat_ids: list[int]

    # Jenkins
    jenkins_url: str
    jenkins_user: str
    jenkins_api_token: str
    jenkins_job_name: str
    jenkins_job_id: str

    # Google Drive OAuth
    google_client_id: str
    google_client_secret: str
    oauth_token_path: Path

    # Bot webhook (Jenkins calls this)
    bot_callback_host: str  # e.g. "http://tg-bot:9090"
    bot_webhook_port: int = 9090

    # Optional
    drive_folder_name: str = ""
    config_ui_url: str = ""

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> Config:
        """Build config with priority: file > env > .env > defaults."""
        load_dotenv()

        resolved_path = config_path
        if resolved_path is None and os.environ.get("CONFIG_PATH"):
            resolved_path = Path(os.environ["CONFIG_PATH"])

        file_data: dict[str, Any] = {}
        if resolved_path and resolved_path.exists():
            file_data = json.loads(resolved_path.read_text())

        def get_value(
            file_key: str,
            env_key: str,
            *,
            default: str = "",
            required: bool = False,
        ) -> str:
            file_value = _nested_get(file_data, file_key)
            if file_value not in (None, ""):
                return str(file_value)

            env_value = os.environ.get(env_key)
            if env_value not in (None, ""):
                return env_value

            if required and default == "":
                raise KeyError(env_key)

            return default

        allowed_chat_ids = _nested_get(file_data, "telegram.allowed_chat_ids")
        if allowed_chat_ids is None:
            allowed_chat_ids = os.environ.get("ALLOWED_CHAT_IDS", "")

        return cls(
            telegram_token=get_value(
                "telegram.bot_token",
                "TELEGRAM_BOT_TOKEN",
                required=True,
            ),
            allowed_chat_ids=_parse_allowed_chat_ids(allowed_chat_ids),
            jenkins_url=get_value(
                "jenkins.url",
                "JENKINS_URL",
                required=True,
            ),
            jenkins_user=get_value(
                "jenkins.user",
                "JENKINS_USER",
                required=True,
            ),
            jenkins_api_token=get_value(
                "jenkins.api_token",
                "JENKINS_API_TOKEN",
                required=True,
            ),
            jenkins_job_name=get_value(
                "jenkins.job_name",
                "JENKINS_JOB_NAME",
                default="flutter-build",
            ),
            jenkins_job_id=get_value(
                "jenkins.job_id",
                "JENKINS_JOB_ID",
                default=get_value(
                    "jenkins.job_name",
                    "JENKINS_JOB_NAME",
                    default="flutter-build",
                ),
            ),
            google_client_id=get_value(
                "drive.client_id",
                "GOOGLE_CLIENT_ID",
                required=True,
            ),
            google_client_secret=get_value(
                "drive.client_secret",
                "GOOGLE_CLIENT_SECRET",
                required=True,
            ),
            oauth_token_path=Path(
                get_value(
                    "drive.oauth_token_path",
                    "BOT_OAUTH_TOKEN_PATH",
                    default=str(_default_oauth_token_path(resolved_path)),
                )
            ),
            bot_callback_host=get_value(
                "bot.callback_host",
                "BOT_CALLBACK_HOST",
                default="http://tg-bot:9090",
            ),
            bot_webhook_port=int(
                get_value(
                    "bot.webhook_port",
                    "BOT_WEBHOOK_PORT",
                    default="9090",
                )
            ),
            drive_folder_name=get_value(
                "drive.folder_name",
                "DRIVE_FOLDER_NAME",
                default="",
            ),
            config_ui_url=get_value(
                "config_ui.url",
                "CONFIG_UI_URL",
                default="",
            ),
        )

    @property
    def bot_callback_url(self) -> str:
        """Full webhook URL that Jenkins calls on build completion."""
        return f"{self.bot_callback_host.rstrip('/')}/webhook/build-complete"
