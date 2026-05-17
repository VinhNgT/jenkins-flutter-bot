"""ConfigHubManager — centralized configuration proxy.

Config-hub has zero domain schemas of its own. All config I/O is
proxied via HTTP to the owning service.  This manager provides
high-level methods that routes delegate to.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

import httpx

from .config import HubBootstrap
from .env_io import (
    build_export_tarball,
    generate_compose_vars,
    generate_env_files,
    import_tarball,
)
from .jenkins_pipeline import generate_jenkinsfile
from .services import ServiceClient

logger = logging.getLogger(__name__)

# Maps UI scope names → internal ServiceClient service names.
# All scopes currently map directly to their service name.  This table exists
# as a seam: if a scope ever needs to diverge from its service name (e.g. a
# second storage backend exposed under a different scope), this is the only
# place to change it.
_SCOPE_TO_SERVICE: dict[str, str] = {
    "bot": "bot",
    "agent": "agent",
    "file_manager": "file_manager",
    "builds": "builds",
}


class ConfigHubManager:
    """Centralized configuration proxy for the JFB stack.

    Instantiated once in ``create_app()`` and attached to ``app.state.manager``.
    Routes call methods on this class rather than wiring up raw dependencies.
    """

    def __init__(self) -> None:
        config = HubBootstrap.load()
        self.file_manager_url: str | None = config.file_manager_url
        self.services = ServiceClient(
            bot_url=config.bot_control_url,
            agent_url=config.agent_control_url,
            file_manager_url=config.file_manager_url,
            build_manager_url=config.build_manager_url,
        )
        self.fm_client = httpx.AsyncClient(timeout=10.0)

    async def start(self) -> None:
        """No-op — config-hub has no daemon to start."""

    async def stop(self) -> None:
        """Shut down reusable HTTP clients."""
        await self.services.close()
        await self.fm_client.aclose()

    async def restart(self) -> None:
        """Restart the manager — re-resolve config and rebuild clients."""
        await self.stop()
        config = HubBootstrap.load()
        self.file_manager_url = config.file_manager_url
        self.services = ServiceClient(
            bot_url=config.bot_control_url,
            agent_url=config.agent_control_url,
            file_manager_url=config.file_manager_url,
            build_manager_url=config.build_manager_url,
        )
        self.fm_client = httpx.AsyncClient(timeout=10.0)
        logger.info("ConfigHubManager restarted")

    def status(self) -> dict[str, Any]:
        """Return standardized status — config-hub is always running."""
        return {
            "configured": True,
            "running": True,
            "last_error": None,
        }

    # ------------------------------------------------------------------
    # Schema aggregation (proxied from all services)
    # ------------------------------------------------------------------

    async def fetch_all_schemas(self) -> dict[str, Any]:
        """Fetch schemas from all managed services."""
        return {
            scope: await self.services.schema(svc)
            for scope, svc in _SCOPE_TO_SERVICE.items()
        }

    # ------------------------------------------------------------------
    # Config CRUD (proxied to owning services)
    # ------------------------------------------------------------------

    async def get_config_for_ui(self) -> dict[str, Any]:
        """Return all config values from all services for the dashboard."""
        result: dict[str, Any] = {}
        secrets_set: dict[str, Any] = {}

        for scope, svc in _SCOPE_TO_SERVICE.items():
            config = await self.services.get_config(svc)
            if config:
                result[scope] = config.get("values", {})
                secrets_set[scope] = config.get("secret_lengths", {})
            else:
                result[scope] = {}
                secrets_set[scope] = {}

        result["_secrets_set"] = secrets_set
        return result

    async def save_scope(self, scope: str, payload: dict[str, Any]) -> None:
        """Proxy a config save to the owning service.

        Raises
        ------
        ValueError
            If *scope* is not a recognised scope name.
        """
        svc = _SCOPE_TO_SERVICE.get(scope)
        if not svc:
            raise ValueError(f"Unknown config scope: {scope}")

        result = await self.services.put_config(svc, payload)
        if result.get("status") == "error":
            detail = result.get("detail", "Unknown error")
            raise RuntimeError(f"Failed to save {scope} config: {detail}")

    # ------------------------------------------------------------------
    # Export / Import (TODO: refactor to HTTP-based)
    # ------------------------------------------------------------------

    async def export_env(self) -> dict[str, Any]:
        """Generate per-service env file contents for preview.

        Fetches config and schemas from all services via HTTP, then
        generates env file content for each service.
        """
        schemas: dict[str, Any] = {}
        configs: dict[str, Any] = {}

        for scope, svc in _SCOPE_TO_SERVICE.items():
            schemas[scope] = await self.services.schema(svc)
            config = await self.services.get_config(svc)
            configs[scope] = config.get("values", {}) if config else {}

        files, warnings = generate_env_files(
            bot_config=configs.get("bot", {}),
            agent_config=configs.get("agent", {}),
            bot_schema=schemas.get("bot"),
            agent_schema=schemas.get("agent"),
            file_manager_config=configs.get("file_manager", {}),
            file_manager_schema=schemas.get("file_manager"),
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
        schemas: dict[str, Any] = {}
        configs: dict[str, Any] = {}

        for scope, svc in _SCOPE_TO_SERVICE.items():
            schemas[scope] = await self.services.schema(svc)
            config = await self.services.get_config(svc)
            configs[scope] = config.get("values", {}) if config else {}

        files, _ = generate_env_files(
            bot_config=configs.get("bot", {}),
            agent_config=configs.get("agent", {}),
            bot_schema=schemas.get("bot"),
            agent_schema=schemas.get("agent"),
            file_manager_config=configs.get("file_manager", {}),
            file_manager_schema=schemas.get("file_manager"),
        )
        return build_export_tarball(files)

    async def import_tarball(self, raw: bytes) -> dict[str, Any]:
        """Import a config tarball, apply changes, and restart services.

        Parses the tarball, extracts env values, converts to JSON config,
        and saves via PUT /control/config to each owning service.
        """
        parsed = import_tarball(
            tarball_bytes=raw,
            bot_schema=await self.services.schema("bot"),
            agent_schema=await self.services.schema("agent"),
            bot_config_path=None,
            agent_config_path=None,
            file_manager_schema=await self.services.schema("file_manager"),
            file_manager_config_path=None,
        )

        # Save each scope's config to the owning service
        for scope, config_data in parsed.configs.items():
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

        return {**dataclasses.asdict(parsed), "restart_results": restart_results}

    # ------------------------------------------------------------------
    # Jenkinsfile (UI quality-of-life feature)
    # ------------------------------------------------------------------

    async def get_jenkinsfile(self) -> dict[str, Any]:
        """Generate Jenkinsfile variants from current build manager config."""
        orch_config = await self.services.get_config("builds")
        values = orch_config.get("values", {}) if orch_config else {}

        # Extract git repo URL and credentials from build manager config
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
