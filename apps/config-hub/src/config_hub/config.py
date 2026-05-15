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
