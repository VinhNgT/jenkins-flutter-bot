"""Admin bot configuration — resolved via Pydantic ServiceSettings."""

from __future__ import annotations

from pydantic import Field
from config_core import ServiceSettings


class AdminBotConfig(ServiceSettings):
    """Resolved admin bot configuration.

    tg-admin-bot has no JSON config file and no control API — it resolves
    all fields from environment variables only.  Using ServiceSettings
    gives it the standard precedence chain and ``.env`` file support.
    """

    bot_token: str = Field(
        "",
        json_schema_extra={"infra": True, "secret": True},
    )
    admin_chat_id: int = Field(
        0,
        json_schema_extra={"infra": True},
    )
    config_hub_url: str = Field(
        "http://config-hub:9000",
        json_schema_extra={"infra": True},
    )
