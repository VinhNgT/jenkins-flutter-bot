"""Config Hub settings — resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Immutable application settings resolved once at startup.

    Env vars:
        BOT_CONTROL_URL           — Base URL of the tg-bot control API
        AGENT_CONTROL_URL         — Base URL of the agent-control API
        FILE_MANAGER_URL          — Base URL of the file-manager API
        ORCHESTRATOR_URL          — Base URL of the build-orchestrator API
    """

    bot_control_url: str | None
    agent_control_url: str | None
    file_manager_url: str | None
    orchestrator_url: str | None

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve settings from environment variables."""
        return cls(
            bot_control_url=os.environ.get("BOT_CONTROL_URL") or None,
            agent_control_url=os.environ.get("AGENT_CONTROL_URL") or None,
            file_manager_url=os.environ.get("FILE_MANAGER_URL") or None,
            orchestrator_url=os.environ.get("ORCHESTRATOR_URL") or None,
        )
