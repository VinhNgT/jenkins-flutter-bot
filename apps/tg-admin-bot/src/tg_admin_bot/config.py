"""Admin bot bootstrap — resolved via Pydantic BootstrapSettings."""

from __future__ import annotations

from pydantic import Field
from config_core import BootstrapSettings


class AdminBotBootstrap(BootstrapSettings):
    """Resolved admin bot bootstrap configuration.

    tg-admin-bot has no JSON config file and no control API — it resolves
    all fields from environment variables only.  Hard crash if required
    fields (bot_token, admin_chat_id) are missing.
    """

    bot_token: str = Field(
        json_schema_extra={"secret": True},
    )
    admin_chat_id: int = Field()
    config_hub_url: str = Field(
        "http://config-hub:9000",
    )
