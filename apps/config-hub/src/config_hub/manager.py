"""ConfigHubManager — centralized configuration proxy.

Config-hub has zero domain schemas of its own. All config I/O is
proxied via HTTP to the owning service.  This manager provides
high-level methods that routes delegate to.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .jenkins_pipeline import generate_jenkinsfile
from .services import ServiceClient
from .settings import Settings

logger = logging.getLogger(__name__)

# All services whose config and schema are proxied through config-hub.
_PROXIED_SERVICES = ("bot", "agent", "file_manager", "orchestrator")

# Scope name → internal service name mapping.
# The web UI uses these scope names in API calls.
_SCOPE_TO_SERVICE = {
    "bot": "bot",
    "agent": "agent",
    "storage": "file_manager",
    "orchestrator": "orchestrator",
}


class ConfigHubManager:
    """Centralized configuration proxy for the JFB stack.

    Instantiated once in ``create_app()`` and attached to ``app.state.manager``.
    Routes call methods on this class rather than wiring up raw dependencies.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.services = ServiceClient(
            bot_url=settings.bot_control_url,
            agent_url=settings.agent_control_url,
            file_manager_url=settings.file_manager_url,
            orchestrator_url=settings.orchestrator_url,
        )
        self.fm_client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        """Shut down reusable HTTP clients."""
        await self.fm_client.aclose()

    # ------------------------------------------------------------------
    # Schema aggregation (proxied from all services)
    # ------------------------------------------------------------------

    async def fetch_all_schemas(self) -> dict[str, Any]:
        """Fetch schemas from all managed services."""
        schemas: dict[str, Any] = {}
        for scope, service in _SCOPE_TO_SERVICE.items():
            schemas[scope] = await self.services.schema(service)
        return schemas

    # ------------------------------------------------------------------
    # Config CRUD (proxied to owning services)
    # ------------------------------------------------------------------

    async def get_config_for_ui(self) -> dict[str, Any]:
        """Return all config values from all services for the dashboard."""
        result: dict[str, Any] = {}
        secrets_set: dict[str, Any] = {}

        for scope, service in _SCOPE_TO_SERVICE.items():
            config = await self.services.get_config(service)
            if config:
                result[scope] = config.get("values", {})
                secrets_set[scope] = config.get("secret_lengths", {})
            else:
                result[scope] = {}
                secrets_set[scope] = {}

        result["_secrets_set"] = secrets_set
        return result

    async def save_scope(self, scope: str, payload: dict[str, Any]) -> None:
        """Proxy a config save to the owning service."""
        service = _SCOPE_TO_SERVICE.get(scope)
        if not service:
            logger.error("Unknown config scope: %s", scope)
            return

        result = await self.services.put_config(service, payload)
        if result.get("status") == "error":
            logger.error("Failed to save %s config: %s", scope, result)

    # ------------------------------------------------------------------
    # Export / Import (TODO: refactor to HTTP-based)
    # ------------------------------------------------------------------

    async def export_env(self) -> dict[str, Any]:
        """Generate per-service env file contents for preview.

        Fetches config and schemas from all services via HTTP, then
        generates env file content for each service.
        """
        from .env_io import generate_compose_vars, generate_env_files

        schemas: dict[str, Any] = {}
        configs: dict[str, Any] = {}

        for scope, service in _SCOPE_TO_SERVICE.items():
            schemas[scope] = await self.services.schema(service)
            config = await self.services.get_config(service)
            configs[scope] = config.get("values", {}) if config else {}

        files, warnings = generate_env_files(
            bot_config=configs.get("bot", {}),
            agent_config=configs.get("agent", {}),
            bot_schema=schemas.get("bot"),
            agent_schema=schemas.get("agent"),
            drive_config=configs.get("storage", {}),
            drive_schema=schemas.get("storage"),
        )
        compose_vars = {
            "bot": generate_compose_vars(
                configs.get("bot", {}), schemas.get("bot"), "Telegram Bot"
            ),
            "agent": generate_compose_vars(
                configs.get("agent", {}), schemas.get("agent"), "Jenkins Agent"
            ),
        }
        return {"files": files, "compose_vars": compose_vars, "warnings": warnings}

    async def export_tarball(self) -> bytes:
        """Build a .tar.gz containing all config as env files."""
        from .env_io import build_export_tarball, generate_env_files

        schemas: dict[str, Any] = {}
        configs: dict[str, Any] = {}

        for scope, service in _SCOPE_TO_SERVICE.items():
            schemas[scope] = await self.services.schema(service)
            config = await self.services.get_config(service)
            configs[scope] = config.get("values", {}) if config else {}

        files, _ = generate_env_files(
            bot_config=configs.get("bot", {}),
            agent_config=configs.get("agent", {}),
            bot_schema=schemas.get("bot"),
            agent_schema=schemas.get("agent"),
            drive_config=configs.get("storage", {}),
            drive_schema=schemas.get("storage"),
        )
        return build_export_tarball(files)

    async def import_tarball(self, raw: bytes) -> dict[str, Any]:
        """Import a config tarball, apply changes, and restart services.

        Parses the tarball, extracts env values, converts to JSON config,
        and saves via PUT /control/config to each owning service.
        """
        from .env_io import parse_import_tarball

        parsed = parse_import_tarball(
            tarball_bytes=raw,
            bot_schema=await self.services.schema("bot"),
            agent_schema=await self.services.schema("agent"),
            drive_schema=await self.services.schema("file_manager"),
        )

        # Save each scope's config to the owning service
        for scope, config_data in parsed.get("configs", {}).items():
            if config_data:
                await self.save_scope(scope, config_data)

        # Auto-restart services to pick up imported config
        restart_results: dict[str, str] = {}
        for scope in ("bot", "agent"):
            try:
                resp = await self.services.restart(scope)
                restart_results[scope] = resp.get("status", "unknown")
            except Exception:
                logger.exception("Failed to restart %s after import", scope)
                restart_results[scope] = "restart_failed"

        return {**parsed, "restart_results": restart_results}

    # ------------------------------------------------------------------
    # Jenkinsfile (UI quality-of-life feature)
    # ------------------------------------------------------------------

    async def get_jenkinsfile(self) -> dict[str, Any]:
        """Generate Jenkinsfile variants from current orchestrator config."""
        orch_config = await self.services.get_config("orchestrator")
        values = orch_config.get("values", {}) if orch_config else {}

        # Extract git repo URL and credentials from orchestrator config
        git_section = values.get("git", {})
        jenkins_section = values.get("jenkins", {})
        repo_url = git_section.get("repo_url", "")
        credentials_id = jenkins_section.get("credentials_id", "")

        warnings: list[str] = []
        if not repo_url:
            repo_url = "<YOUR_REPO_URL>"
            warnings.append(
                "Repository URL not configured — update it in"
                " the Orchestrator config tab."
            )

        effective_credentials_id = credentials_id or "<YOUR_CREDENTIALS_ID>"
        if not credentials_id:
            warnings.append(
                "Repo Credentials ID not configured — the private script uses a "
                "placeholder. Set it in the Orchestrator config tab or edit the Jenkinsfile."
            )

        script_public = generate_jenkinsfile(repo_url, credentials_id="")
        script_private = generate_jenkinsfile(repo_url, effective_credentials_id)
        return {
            "script_public": script_public,
            "script_private": script_private,
            "warnings": warnings,
        }
