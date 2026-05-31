"""Service-hub bootstrap — inter-service URLs resolved at process start."""

from __future__ import annotations

from pydantic import Field
from config_core import BootstrapSettings


class ServiceHubBootstrap(BootstrapSettings):
    """Resolved service-hub bootstrap configuration.

    All fields are env-only — service-hub owns no user-facing schema
    (it proxies schemas from the owning services).
    """

    agent_control_url: str | None = Field(None)
    file_manager_url: str | None = Field(None)
    build_manager_url: str | None = Field(None)
