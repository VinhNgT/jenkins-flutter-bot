"""StackManager — the central operational hub.

Owns all shared state (config paths, ServiceClient, BuildOrchestrator,
file-manager proxy) and provides high-level methods that routes
delegate to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from config_schema import deep_merge, nested_get, serialize_schema

from .config_store import (
    clean_secrets_from_payload,
    extract_secret_fields,
    load_json,
    secrets_set,
    strip_secrets,
    write_json,
)
from .builds.orchestrator import BuildOrchestrator
from .env_io import (
    build_export_tarball,
    generate_compose_vars,
    generate_env_files,
    import_tarball,
)
from .jenkins_pipeline import generate_jenkinsfile
from .schema import (
    DRIVE_FIELDS,
    DRIVE_INFRA,
    DRIVE_MODULE_DESCRIPTION,
    DRIVE_MODULE_TITLE,
    DRIVE_SECRET_FIELDS,
)
from .services import ServiceClient
from .settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfigPaths:
    """Resolved filesystem paths for all config JSON files."""

    bot: Path | None
    agent: Path | None
    drive: Path | None

    @classmethod
    def from_settings(cls, settings: Settings) -> ConfigPaths:
        """Derive config paths from settings."""
        return cls(
            bot=settings.bot_config_path,
            agent=settings.agent_config_path,
            drive=settings.drive_config_path,
        )


class StackManager:
    """Central operational hub for the JFB stack.

    Instantiated once in ``create_app()`` and attached to ``app.state.manager``.
    Routes call methods on this class rather than wiring up raw dependencies.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.paths = ConfigPaths.from_settings(settings)
        self.services = ServiceClient(
            bot_url=settings.bot_control_url,
            agent_url=settings.agent_control_url,
            file_manager_url=settings.file_manager_url,
        )
        self.orchestrator = BuildOrchestrator(
            data_dir=settings.build_data_path,
            sm_service_url=settings.sm_service_url,
            file_manager_url=settings.file_manager_url or "http://file-manager:9092",
        )
        self.fm_client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        """Shut down reusable HTTP clients."""
        await self.fm_client.aclose()

    # ------------------------------------------------------------------
    # Config I/O
    # ------------------------------------------------------------------

    def _scope_path(self, scope: str) -> Path | None:
        return {
            "bot": self.paths.bot,
            "agent": self.paths.agent,
            "drive": self.paths.drive,
        }.get(scope)

    def load_config(self, scope: str) -> dict[str, Any]:
        """Load a config JSON file by scope name."""
        if scope == "storage":
            return self._fetch_storage_config_sync()
        return load_json(self._scope_path(scope))

    def _fetch_storage_config_sync(self) -> dict[str, Any]:
        """Fetch current config from file-manager (blocking fallback).

        Config routes are sync so we use the sync httpx client here.
        For production the storage config should be fetched async.
        """
        url = self.settings.file_manager_url
        if not url:
            return {}
        try:
            resp = httpx.get(f"{url}/control/config", timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception("Failed to fetch storage config")
            return {}

    def save_config(
        self,
        scope: str,
        patch: dict[str, Any],
        secret_fields: tuple[str, ...] = (),
    ) -> None:
        """Deep-merge *patch* into the existing config and write."""
        path = self._scope_path(scope)
        cleaned = clean_secrets_from_payload(patch, secret_fields)
        existing = load_json(path)
        merged = deep_merge(existing, cleaned)
        write_json(path, merged)

    # ------------------------------------------------------------------
    # Schema aggregation
    # ------------------------------------------------------------------

    async def fetch_all_schemas(self) -> dict[str, Any]:
        """Fetch schemas from bot/agent/file-manager services, plus local drive schema."""
        schemas: dict[str, Any] = {
            "bot": await self.services.schema("bot"),
            "agent": await self.services.schema("agent"),
            "drive": serialize_schema(
                DRIVE_FIELDS, DRIVE_MODULE_TITLE, DRIVE_MODULE_DESCRIPTION
            ),
            "storage": await self.services.schema("file_manager"),
        }
        return schemas

    async def _service_schemas(
        self,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Fetch bot and agent schemas from their control APIs."""
        return await self.services.schema("bot"), await self.services.schema("agent")

    # ------------------------------------------------------------------
    # Config CRUD (with secret masking for the web UI)
    # ------------------------------------------------------------------

    async def get_config_for_ui(self) -> dict[str, Any]:
        """Return all config values with secrets stripped for the browser."""
        bot_schema, agent_schema = await self._service_schemas()
        bot_secrets = extract_secret_fields(bot_schema)
        agent_secrets = extract_secret_fields(agent_schema)

        raw = {
            "bot": load_json(self.paths.bot),
            "agent": load_json(self.paths.agent),
            "drive": load_json(self.paths.drive),
        }

        return {
            "bot": strip_secrets(raw["bot"], bot_secrets),
            "agent": strip_secrets(raw["agent"], agent_secrets),
            "drive": strip_secrets(raw["drive"], DRIVE_SECRET_FIELDS),
            "_secrets_set": {
                "bot": secrets_set(raw["bot"], bot_secrets),
                "agent": secrets_set(raw["agent"], agent_secrets),
                "drive": secrets_set(raw["drive"], DRIVE_SECRET_FIELDS),
            },
        }

    async def save_scope(self, scope: str, payload: dict[str, Any]) -> None:
        """Save config for a scope, determining secrets dynamically."""
        if scope == "storage":
            await self._save_storage_config(payload)
            return
        if scope == "drive":
            secret_fields = DRIVE_SECRET_FIELDS
        else:
            schema = await self.services.schema(scope)
            secret_fields = extract_secret_fields(schema)
        self.save_config(scope, payload, secret_fields)

    async def _save_storage_config(self, payload: dict[str, Any]) -> None:
        """Proxy a config save to the file-manager service."""
        url = self.settings.file_manager_url
        if not url:
            logger.error("Cannot save storage config — file_manager_url not set")
            return
        try:
            resp = await self.fm_client.put(
                f"{url}/control/config",
                json=payload,
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to save storage config via file-manager")

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    async def export_env(self) -> dict[str, Any]:
        """Generate per-service env file contents for preview."""
        bot_schema, agent_schema = await self._service_schemas()
        drive_schema = serialize_schema(
            DRIVE_FIELDS, DRIVE_MODULE_TITLE, DRIVE_MODULE_DESCRIPTION
        )
        drive_schema["infra"] = serialize_schema(
            DRIVE_INFRA, DRIVE_MODULE_TITLE, DRIVE_MODULE_DESCRIPTION
        )["fields"]

        bot_data = load_json(self.paths.bot)
        agent_data = load_json(self.paths.agent)
        drive_data = load_json(self.paths.drive)

        files, warnings = generate_env_files(
            bot_config=bot_data,
            agent_config=agent_data,
            bot_schema=bot_schema,
            agent_schema=agent_schema,
            drive_config=drive_data,
            drive_schema=drive_schema,
        )
        compose_vars = {
            "bot": generate_compose_vars(bot_data, bot_schema, "Telegram Bot"),
            "agent": generate_compose_vars(
                agent_data, agent_schema, "Jenkins Agent"
            ),
        }
        return {"files": files, "compose_vars": compose_vars, "warnings": warnings}

    async def export_tarball(self) -> bytes:
        """Build a .tar.gz containing all config files."""
        bot_schema, agent_schema = await self._service_schemas()
        drive_schema = serialize_schema(
            DRIVE_FIELDS, DRIVE_MODULE_TITLE, DRIVE_MODULE_DESCRIPTION
        )
        drive_schema["infra"] = serialize_schema(
            DRIVE_INFRA, DRIVE_MODULE_TITLE, DRIVE_MODULE_DESCRIPTION
        )["fields"]

        files, _ = generate_env_files(
            bot_config=load_json(self.paths.bot),
            agent_config=load_json(self.paths.agent),
            bot_schema=bot_schema,
            agent_schema=agent_schema,
            drive_config=load_json(self.paths.drive),
            drive_schema=drive_schema,
        )
        return build_export_tarball(files)

    async def import_tarball(self, raw: bytes) -> dict[str, Any]:
        """Import a config tarball, apply changes, and restart services."""
        bot_schema, agent_schema = await self._service_schemas()
        drive_schema = serialize_schema(
            DRIVE_FIELDS, DRIVE_MODULE_TITLE, DRIVE_MODULE_DESCRIPTION
        )

        result = import_tarball(
            tarball_bytes=raw,
            bot_schema=bot_schema,
            agent_schema=agent_schema,
            bot_config_path=self.paths.bot,
            agent_config_path=self.paths.agent,
            drive_schema=drive_schema,
            drive_config_path=self.paths.drive,
        )

        # Auto-restart services to pick up imported config
        restart_results: dict[str, str] = {}
        for scope in ("bot", "agent"):
            try:
                resp = await self.services.restart(scope)
                restart_results[scope] = resp.get("status", "unknown")
            except Exception:
                logger.exception("Failed to restart %s after import", scope)
                restart_results[scope] = "restart_failed"

        from dataclasses import asdict

        return {**asdict(result), "restart_results": restart_results}

    # ------------------------------------------------------------------
    # Jenkinsfile
    # ------------------------------------------------------------------

    def get_jenkinsfile(self) -> dict[str, Any]:
        """Generate both public and private Jenkinsfile variants from current config.

        Always returns two scripts:
        - ``script_public``: plain ``git`` step, no credentials.
        - ``script_private``: ``checkout`` step using a Jenkins saved credential
          (the configured ``credentials_id``, or a placeholder if not set).
        """
        bot_data = self.load_config("bot")
        repo_url = nested_get(bot_data, "git.repo_url") or ""
        credentials_id = nested_get(bot_data, "jenkins.credentials_id") or ""

        warnings: list[str] = []
        if not repo_url:
            repo_url = "<YOUR_REPO_URL>"
            warnings.append(
                "Repository URL not configured — update it in the Bot config tab."
            )

        effective_credentials_id = credentials_id or "<YOUR_CREDENTIALS_ID>"
        if not credentials_id:
            warnings.append(
                "Repo Credentials ID not configured — the private script uses a "
                "placeholder. Set it in the Bot config tab or edit the Jenkinsfile."
            )

        script_public = generate_jenkinsfile(repo_url, credentials_id="")
        script_private = generate_jenkinsfile(repo_url, effective_credentials_id)
        return {
            "script_public": script_public,
            "script_private": script_private,
            "warnings": warnings,
        }
