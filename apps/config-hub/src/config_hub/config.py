"""Config-hub bootstrap — inter-service URLs resolved at process start."""

from __future__ import annotations

from pydantic import Field
from config_core import BootstrapSettings


class HubBootstrap(BootstrapSettings):
    """Resolved config-hub bootstrap configuration.

    All fields are env-only — config-hub owns no user-facing schema
    (it proxies schemas from the owning services).
    """

    bot_control_url: str | None = Field(None)
    agent_control_url: str | None = Field(None)
    file_manager_url: str | None = Field(None)
    build_manager_url: str | None = Field(None)
    auth_username: str | None = Field(
        None,
        description="Username for Web UI Basic Authentication",
    )
    auth_password: str | None = Field(
        None,
        description="Password for Web UI Basic Authentication",
    )
