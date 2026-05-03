"""FastAPI app for stack configuration and service control."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .drive import DriveOAuthManager

MASKED_VALUE = "********"
BOT_SECRET_FIELDS = (
    "telegram.bot_token",
    "jenkins.api_token",
    "drive.client_secret",
)
AGENT_SECRET_FIELDS = ("agent.secret",)
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"


def _drive_token_path(bot_config_path: Path | None) -> Path:
    if bot_config_path is not None:
        return bot_config_path.parent / "oauth.json"
    return Path("data/oauth.json")


def _nested_get(data: dict[str, Any], dotted_key: str) -> Any:
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _nested_set(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    current = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _deep_merge(existing: Any, incoming: Any) -> Any:
    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = {**existing}
        for key, value in incoming.items():
            merged[key] = _deep_merge(merged.get(key), value)
        return merged
    return incoming


def _mask_secrets(
    data: dict[str, Any], secret_fields: tuple[str, ...]
) -> dict[str, Any]:
    masked = json.loads(json.dumps(data))
    for field in secret_fields:
        if _nested_get(masked, field) not in (None, ""):
            _nested_set(masked, field, MASKED_VALUE)
    return masked


def _restore_masked_secrets(
    merged: dict[str, Any],
    incoming: dict[str, Any],
    existing: dict[str, Any],
    secret_fields: tuple[str, ...],
) -> dict[str, Any]:
    for field in secret_fields:
        if _nested_get(incoming, field) == MASKED_VALUE:
            existing_value = _nested_get(existing, field)
            if existing_value not in (None, ""):
                _nested_set(merged, field, existing_value)
    return merged


@dataclass(frozen=True)
class Settings:
    bot_control_url: str | None
    agent_control_url: str | None
    bot_config_path: Path | None
    agent_config_path: Path | None

    @classmethod
    def from_env(cls) -> Settings:
        bot_config_path = os.environ.get("BOT_CONFIG_PATH")
        agent_config_path = os.environ.get("AGENT_CONFIG_PATH")
        return cls(
            bot_control_url=os.environ.get("BOT_CONTROL_URL") or None,
            agent_control_url=os.environ.get("AGENT_CONTROL_URL") or None,
            bot_config_path=Path(bot_config_path) if bot_config_path else None,
            agent_config_path=Path(agent_config_path) if agent_config_path else None,
        )


class ServiceClient:
    """Call bot and agent control endpoints."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def _control(self, service: str, action: str | None = None) -> dict[str, Any]:
        url = self._service_url(service)
        if not url:
            return {
                "available": False,
                "running": False,
                "detail": "service URL not configured",
            }

        target = (
            f"{url}/control/status" if action is None else f"{url}/control/{action}"
        )
        method = "GET" if action is None else "POST"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.request(method, target)
                response.raise_for_status()
                data = response.json()
                data["available"] = True
                return data
        except Exception as exc:
            return {
                "available": False,
                "running": False,
                "detail": str(exc),
            }

    def _service_url(self, service: str) -> str | None:
        if service == "bot":
            return self._settings.bot_control_url
        if service == "agent":
            return self._settings.agent_control_url
        raise ValueError(f"Unknown service: {service}")

    async def status(self, service: str) -> dict[str, Any]:
        return await self._control(service)

    async def start(self, service: str) -> dict[str, Any]:
        return await self._control(service, "start")

    async def stop(self, service: str) -> dict[str, Any]:
        return await self._control(service, "stop")

    async def restart(self, service: str) -> dict[str, Any]:
        return await self._control(service, "restart")


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text())


def _write_json(path: Path | None, data: dict[str, Any]) -> None:
    if path is None:
        raise HTTPException(status_code=500, detail="Config path not set")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _drive_credentials(
    bot_config: dict[str, Any],
) -> tuple[str | None, str | None]:
    client_id = _nested_get(bot_config, "drive.client_id")
    client_secret = _nested_get(bot_config, "drive.client_secret")
    return (
        str(client_id) if client_id not in (None, "") else None,
        str(client_secret) if client_secret not in (None, "") else None,
    )


def _drive_callback_url(request: Request) -> str:
    return str(request.url_for("drive_oauth_callback"))


def create_app() -> FastAPI:
    """Create and configure the config-ui FastAPI application."""
    app = FastAPI(title="config-ui")
    settings = Settings.from_env()
    app.state.settings = settings
    app.state.service_client = ServiceClient(settings)
    app.state.drive_oauth = DriveOAuthManager(
        _drive_token_path(settings.bot_config_path)
    )
    app.state.templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    _register_routes(app)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


def _register_routes(app: FastAPI) -> None:
    """Register all routes on the app instance."""

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/config")
    async def get_config(request: Request) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        bot = _load_json(settings.bot_config_path)
        agent = _load_json(settings.agent_config_path)
        return {
            "bot": _mask_secrets(bot, BOT_SECRET_FIELDS),
            "agent": _mask_secrets(agent, AGENT_SECRET_FIELDS),
        }

    @app.post("/api/config")
    async def save_config(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        incoming_bot = payload.get("bot", {})
        incoming_agent = payload.get("agent", {})

        if not isinstance(incoming_bot, dict) or not isinstance(incoming_agent, dict):
            raise HTTPException(status_code=400, detail="Invalid config payload")

        existing_bot = _load_json(settings.bot_config_path)
        existing_agent = _load_json(settings.agent_config_path)

        merged_bot = _deep_merge(existing_bot, incoming_bot)
        merged_agent = _deep_merge(existing_agent, incoming_agent)
        merged_bot = _restore_masked_secrets(
            merged_bot, incoming_bot, existing_bot, BOT_SECRET_FIELDS
        )
        merged_agent = _restore_masked_secrets(
            merged_agent, incoming_agent, existing_agent, AGENT_SECRET_FIELDS
        )

        _write_json(settings.bot_config_path, merged_bot)
        _write_json(settings.agent_config_path, merged_agent)
        return {"saved": True}

    @app.get("/api/drive/status")
    async def get_drive_status(request: Request) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        drive_oauth: DriveOAuthManager = request.app.state.drive_oauth
        bot = _load_json(settings.bot_config_path)
        client_id, client_secret = _drive_credentials(bot)

        if not client_id or not client_secret:
            return {
                "configured": False,
                "connected": False,
                "auth_pending": drive_oauth.auth_pending,
                "token_path": str(drive_oauth.token_path),
            }

        status = drive_oauth.status(client_id, client_secret)
        status["configured"] = True
        return status

    @app.get("/api/drive/oauth/callback")
    async def drive_oauth_callback(request: Request) -> Any:
        drive_oauth: DriveOAuthManager = request.app.state.drive_oauth
        templates: Jinja2Templates = request.app.state.templates
        error = request.query_params.get("error")

        if error:
            description = request.query_params.get("error_description")
            message = "Google authorization was not completed."
            if description:
                message = f"{message} {description}"
            return templates.TemplateResponse(
                request=request,
                name="oauth_callback.html",
                context={
                    "title": "Google Drive Connection Failed",
                    "message": message,
                    "payload_json": json.dumps(
                        {"type": "drive-oauth-complete", "success": False, "message": message}
                    ),
                },
                status_code=400,
            )

        try:
            drive_oauth.exchange_callback(str(request.url))
        except RuntimeError as exc:
            return templates.TemplateResponse(
                request=request,
                name="oauth_callback.html",
                context={
                    "title": "Google Drive Connection Failed",
                    "message": str(exc),
                    "payload_json": json.dumps(
                        {"type": "drive-oauth-complete", "success": False, "message": str(exc)}
                    ),
                },
                status_code=400,
            )
        except Exception as exc:
            msg = f"Drive authorization failed: {exc}"
            return templates.TemplateResponse(
                request=request,
                name="oauth_callback.html",
                context={
                    "title": "Google Drive Connection Failed",
                    "message": msg,
                    "payload_json": json.dumps(
                        {"type": "drive-oauth-complete", "success": False, "message": msg}
                    ),
                },
                status_code=400,
            )

        message = "Google Drive is connected. You can return to the dashboard."
        return templates.TemplateResponse(
            request=request,
            name="oauth_callback.html",
            context={
                "title": "Google Drive Connected",
                "message": message,
                "payload_json": json.dumps(
                    {"type": "drive-oauth-complete", "success": True, "message": message}
                ),
            },
        )

    @app.post("/api/drive/connect/start")
    async def start_drive_connect(request: Request) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        drive_oauth: DriveOAuthManager = request.app.state.drive_oauth
        bot = _load_json(settings.bot_config_path)
        client_id, client_secret = _drive_credentials(bot)

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=400,
                detail="Configure the bot Google Drive client ID and client secret first.",
            )

        return {
            "auth_url": drive_oauth.start(
                client_id,
                client_secret,
                _drive_callback_url(request),
            )
        }

    @app.get("/api/services/status")
    async def get_service_status(request: Request) -> dict[str, Any]:
        client: ServiceClient = request.app.state.service_client
        return {
            "bot": await client.status("bot"),
            "agent": await client.status("agent"),
        }

    @app.post("/api/services/{service}/{action}")
    async def control_service(
        request: Request, service: str, action: str
    ) -> dict[str, Any]:
        if service not in {"bot", "agent"}:
            raise HTTPException(status_code=404, detail="Unknown service")
        if action not in {"start", "stop", "restart"}:
            raise HTTPException(status_code=404, detail="Unknown action")

        client: ServiceClient = request.app.state.service_client
        if action == "start":
            return await client.start(service)
        if action == "stop":
            return await client.stop(service)
        return await client.restart(service)
