"""Admin bot settings — resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Settings for the admin bot, resolved from environment variables.

    Env vars:
        ADMIN_BOT_TOKEN      — Telegram bot token for the admin bot
        ADMIN_CHAT_ID        — Telegram chat ID authorized for admin commands
        CONFIG_HUB_URL       — Base URL of the config-hub API
    """

    bot_token: str
    admin_chat_id: int
    config_hub_url: str

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve settings from environment variables."""
        token = os.environ.get("ADMIN_BOT_TOKEN", "")
        chat_id_str = os.environ.get("ADMIN_CHAT_ID", "0")
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            chat_id = 0

        return cls(
            bot_token=token,
            admin_chat_id=chat_id,
            config_hub_url=os.environ.get("CONFIG_HUB_URL", "http://config-hub:9000"),
        )
