"""Config-hub configuration — inter-service URLs resolved via Pydantic."""

from __future__ import annotations

from pydantic import Field
from config_core import ServiceSettings


class HubConfig(ServiceSettings):
    """Resolved config-hub configuration.

    All fields are infrastructure-only — config-hub owns no user-facing
    schema (it proxies schemas from the owning services).
    """

    bot_control_url: str | None = Field(
        None,
        json_schema_extra={"infra": True},
    )
    agent_control_url: str | None = Field(
        None,
        json_schema_extra={"infra": True},
    )
    file_manager_url: str | None = Field(
        None,
        json_schema_extra={"infra": True},
    )
    build_manager_url: str | None = Field(
        None,
        json_schema_extra={"infra": True},
    )
