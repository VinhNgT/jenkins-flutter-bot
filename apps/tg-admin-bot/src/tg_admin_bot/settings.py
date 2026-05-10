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
        STACK_MANAGER_URL    — Base URL of the stack-manager API
    """

    bot_token: str
    admin_chat_id: int
    stack_manager_url: str

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
            stack_manager_url=os.environ.get(
                "STACK_MANAGER_URL", "http://stack-manager:9000"
            ),
        )
