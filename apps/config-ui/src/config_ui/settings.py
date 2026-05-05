"""Config-UI settings resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Immutable application settings resolved once at startup."""

    bot_control_url: str | None
    agent_control_url: str | None
    bot_config_path: Path | None
    agent_config_path: Path | None
    ui_config_path: Path | None

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve settings from environment variables."""
        bot_config_path = os.environ.get("BOT_CONFIG_PATH")
        agent_config_path = os.environ.get("AGENT_CONFIG_PATH")
        ui_config_path = os.environ.get("UI_CONFIG_PATH")
        return cls(
            bot_control_url=os.environ.get("BOT_CONTROL_URL") or None,
            agent_control_url=os.environ.get("AGENT_CONTROL_URL") or None,
            bot_config_path=Path(bot_config_path) if bot_config_path else None,
            agent_config_path=Path(agent_config_path) if agent_config_path else None,
            ui_config_path=Path(ui_config_path) if ui_config_path else None,
        )
