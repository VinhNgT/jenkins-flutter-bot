"""Bot configuration resolved from declarative schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import BOT_FIELDS, post_resolve, resolve_fields


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
    jenkins_credentials_id: str

    # Google Drive
    oauth_token_path: Path

    # Bot webhook (Jenkins calls this)
    bot_callback_base_url: str
    bot_webhook_port: int

    # Optional
    drive_folder_name: str
    app_name: str
    max_recent_builds: int
    build_timeout: int
    admin_contact: str
    config_ui_url: str

    # Git repository (optional — enables commit comparison)
    git_repo_url: str
    git_access_token: str

    @property
    def commit_check_enabled(self) -> bool:
        """Whether duplicate commit detection is configured."""
        return bool(self.git_repo_url)

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> Config:
        """Build config with priority: file > env > .env > defaults."""
        values = resolve_fields(BOT_FIELDS, config_path)
        values = post_resolve(values, config_path)
        return cls(**values)

    @property
    def bot_callback_url(self) -> str:
        """Full webhook URL that Jenkins calls on build completion."""
        return f"{self.bot_callback_base_url.rstrip('/')}/webhook/build-complete"
