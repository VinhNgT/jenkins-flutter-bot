"""Config-hub bootstrap — inter-service URLs resolved at process start."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field, field_validator, model_validator
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
    enable_browser_preview: bool = Field(
        False,
        description="Enable administrative access via standard desktop web browser for local development/preview",
    )
    browser_auth_username: str | None = Field(
        None,
        description="Username for Basic Authentication in browser preview mode",
    )
    browser_auth_password: str | None = Field(
        None,
        description="Password for Basic Authentication in browser preview mode",
    )
    telegram_bot_token: str | None = Field(
        None,
        description="Bot token for validating Telegram initData signatures",
    )
    admin_telegram_user_ids: list[int] = Field(
        default_factory=list,
        description="Telegram user IDs authorized for admin access",
    )

    @field_validator("admin_telegram_user_ids", mode="before")
    @classmethod
    def parse_admin_user_ids(cls, v: Any) -> list[int]:
        """Coerce comma-separated strings and bare integers into a list."""
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [int(x) for x in parsed]
                except Exception:
                    pass
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return v

    @model_validator(mode="after")
    def validate_preview_credentials(self) -> HubBootstrap:
        """Ensure preview basic auth credentials are provided when preview is enabled."""
        if self.enable_browser_preview:
            if not self.browser_auth_username or not self.browser_auth_password:
                raise ValueError(
                    "BROWSER_AUTH_USERNAME and BROWSER_AUTH_PASSWORD are required when ENABLE_BROWSER_PREVIEW is enabled"
                )
        return self
