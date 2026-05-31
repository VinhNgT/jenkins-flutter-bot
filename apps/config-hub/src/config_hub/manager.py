"""ConfigHubManager — centralized configuration proxy.

Config-hub has zero domain schemas of its own. All config I/O is
proxied via HTTP to the owning service.  This manager provides
high-level methods that routes delegate to.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Any, cast

import httpx

from .config import HubBootstrap
from .env_io import (
    build_export_tarball,
    generate_compose_env,
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

    def __init__(
        self,
        *,
        config: HubBootstrap | None = None,
        service_client: ServiceClient | None = None,
        fm_client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved = config or HubBootstrap.load()
        self.file_manager_url: str | None = resolved.file_manager_url
        self.enable_browser_preview: bool = resolved.enable_browser_preview
        self.browser_auth_username: str | None = resolved.browser_auth_username
        self.browser_auth_password: str | None = resolved.browser_auth_password
        self.telegram_bot_token: str | None = resolved.telegram_bot_token
        self.admin_telegram_user_ids: list[int] = resolved.admin_telegram_user_ids
        self.services = service_client or ServiceClient(
            bot_url=resolved.bot_control_url,
            agent_url=resolved.agent_control_url,
            file_manager_url=resolved.file_manager_url,
            build_manager_url=resolved.build_manager_url,
        )
        self.fm_client = fm_client or httpx.AsyncClient(timeout=10.0)

    async def start(self) -> None:
        """No-op — config-hub has no daemon to start."""

    async def stop(self) -> None:
        """Shut down reusable HTTP clients."""
        await self.services.close()
        await self.fm_client.aclose()

    async def restart(self, config: HubBootstrap | None = None) -> None:
        """Restart the manager — re-resolve config and rebuild clients."""
        await self.stop()
        resolved = config or HubBootstrap.load()
        self.file_manager_url = resolved.file_manager_url
        self.enable_browser_preview = resolved.enable_browser_preview
        self.browser_auth_username = resolved.browser_auth_username
        self.browser_auth_password = resolved.browser_auth_password
        self.telegram_bot_token = resolved.telegram_bot_token
        self.admin_telegram_user_ids = resolved.admin_telegram_user_ids
        self.services = ServiceClient(
            bot_url=resolved.bot_control_url,
            agent_url=resolved.agent_control_url,
            file_manager_url=resolved.file_manager_url,
            build_manager_url=resolved.build_manager_url,
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
        """Fetch schemas from all managed services concurrently."""
        scopes = list(_SCOPE_TO_SERVICE.keys())
        services = list(_SCOPE_TO_SERVICE.values())
        results = await asyncio.gather(*(self.services.schema(s) for s in services))
        return dict(zip(scopes, results))

    # ------------------------------------------------------------------
    # Config CRUD (proxied to owning services)
    # ------------------------------------------------------------------

    async def get_config_for_ui(self) -> dict[str, Any]:
        """Return all config values from all services concurrently."""
        scopes = list(_SCOPE_TO_SERVICE.keys())
        services = list(_SCOPE_TO_SERVICE.values())
        configs = await asyncio.gather(*(self.services.get_config(s) for s in services))

        result: dict[str, Any] = {}
        for scope, config in zip(scopes, configs):
            if config:
                result[scope] = {
                    "values": config.get("values", {}),
                    "secret_lengths": config.get("secret_lengths", {}),
                }
            else:
                result[scope] = {
                    "values": {},
                    "secret_lengths": {},
                }

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
        """Generate compose.env file contents for preview.

        Fetches config and schemas from all services concurrently via HTTP, then
        generates the compose.env content.
        """
        scopes = list(_SCOPE_TO_SERVICE.keys())
        services = list(_SCOPE_TO_SERVICE.values())

        schema_calls = [self.services.schema(s) for s in services]
        config_calls = [self.services.get_config_unmasked(s) for s in services]

        fetched = await asyncio.gather(*schema_calls, *config_calls)

        fetched_schemas = fetched[: len(services)]
        fetched_configs = fetched[len(services) :]

        schemas = dict(zip(scopes, fetched_schemas))
        configs = {
            scope: (config if config else {})
            for scope, config in zip(scopes, fetched_configs)
        }

        compose_env_str, warnings = generate_compose_env(
            bot_config=configs.get("bot", {}),
            agent_config=configs.get("agent", {}),
            bot_schema=schemas.get("bot"),
            agent_schema=schemas.get("agent"),
            file_manager_config=configs.get("file_manager", {}),
            file_manager_schema=schemas.get("file_manager"),
            builds_config=configs.get("builds", {}),
            builds_schema=schemas.get("builds"),
        )
        return {"compose_env": compose_env_str, "warnings": warnings}

    async def export_tarball(self) -> bytes:
        """Build a .tar.gz containing compose.env and all json/ovpn data."""
        scopes = list(_SCOPE_TO_SERVICE.keys())
        services = list(_SCOPE_TO_SERVICE.values())

        # Parallel fetch of all schemas, unmasked configs, and files
        schema_calls = [self.services.schema(s) for s in services]
        config_calls = [self.services.get_config_unmasked(s) for s in services]

        fetched = await asyncio.gather(
            *schema_calls,
            *config_calls,
            self.services.download_vpn_file(),
            self.services.get_oauth_token(),
        )

        fetched_schemas = cast(list[Any], fetched[: len(services)])
        fetched_configs = cast(list[Any], fetched[len(services) : len(services) * 2])
        vpn_file = cast(bytes | None, fetched[-2])
        oauth_token = cast(dict[str, Any] | None, fetched[-1])

        schemas = cast(dict[str, dict[str, Any] | None], dict(zip(scopes, fetched_schemas)))
        configs = cast(
            dict[str, dict[str, Any]],
            {
                scope: (config if isinstance(config, dict) else {})
                for scope, config in zip(scopes, fetched_configs)
            }
        )

        compose_env_str, _ = generate_compose_env(
            bot_config=configs.get("bot", {}),
            agent_config=configs.get("agent", {}),
            bot_schema=schemas.get("bot"),
            agent_schema=schemas.get("agent"),
            file_manager_config=configs.get("file_manager", {}),
            file_manager_schema=schemas.get("file_manager"),
            builds_config=configs.get("builds", {}),
            builds_schema=schemas.get("builds"),
        )
        return build_export_tarball(
            compose_env=compose_env_str,
            json_configs=configs,
            oauth_token=oauth_token,
            vpn_file=vpn_file,
        )

    async def import_tarball(self, raw: bytes) -> dict[str, Any]:
        """Import a config tarball, apply changes, and restart services.

        Parses the tarball, extracts env values, converts to JSON config,
        and saves via PUT /control/config to each owning service.
        """
        (
            bot_schema,
            agent_schema,
            file_manager_schema,
            builds_schema,
        ) = await asyncio.gather(
            self.services.schema("bot"),
            self.services.schema("agent"),
            self.services.schema("file_manager"),
            self.services.schema("builds"),
        )

        parsed = import_tarball(
            tarball_bytes=raw,
            bot_schema=bot_schema,
            agent_schema=agent_schema,
            file_manager_schema=file_manager_schema,
            builds_schema=builds_schema,
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

    async def get_jenkinsfile(
        self,
        discard_builds: bool = True,
        clean_workspace: bool = False,
        shallow_clone: bool = True,
        repo_url: str | None = None,
        credentials_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate Jenkinsfile variants from current parameters or config."""
        # Fall back to builds config if parameters are not provided explicitly
        if not repo_url or not credentials_id:
            orch_config = await self.services.get_config("builds")
            values = orch_config.get("values", {}) if orch_config else {}
            git_section = values.get("git", {})
            jenkins_section = values.get("jenkins", {})
            if not repo_url:
                repo_url = git_section.get("repo_url", "")
            if not credentials_id:
                credentials_id = jenkins_section.get("credentials_id", "")

        warnings: list[str] = []
        if not repo_url:
            repo_url = "<YOUR_REPO_URL>"
            warnings.append(
                "Repository URL not configured — update it in the settings above."
            )

        effective_credentials_id = credentials_id or "<YOUR_CREDENTIALS_ID>"
        if not credentials_id:
            warnings.append(
                "Repo Credentials ID not configured — the private script uses a "
                "placeholder. Set it in the settings above or edit the Jenkinsfile."
            )

        script_public = generate_jenkinsfile(
            repo_url,
            credentials_id="",
            discard_builds=discard_builds,
            clean_workspace=clean_workspace,
            shallow_clone=shallow_clone,
        )
        script_private = generate_jenkinsfile(
            repo_url,
            effective_credentials_id,
            discard_builds=discard_builds,
            clean_workspace=clean_workspace,
            shallow_clone=shallow_clone,
        )
        return {
            "script_public": script_public,
            "script_private": script_private,
            "warnings": warnings,
        }
