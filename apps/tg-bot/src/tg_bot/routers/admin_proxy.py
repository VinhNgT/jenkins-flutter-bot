"""Admin Proxy router — handles /api/webapp-admin/* endpoints.

Authenticates Telegram initData / Basic Auth, proxies configs to/from service-hub,
and manages local bot settings and lifecycle.
"""

from __future__ import annotations

import io
import json
import logging
import pathlib
import tarfile
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from config_core import (
    get_buffer_logs,
    get_frontend_schema,
    read_masked_config,
    save_config_with_merge,
)

from ..config import BotSettings, _DEFAULT_CONFIG_PATH
from ..dependencies import ManagerDep, verify_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webapp-admin", tags=["admin-proxy"])

_SCOPE_MAP = {
    "bot": "bot",
    "agent": "agent-control",
    "builds": "build-manager",
    "file_manager": "file-manager",
}

# Template engine setup (relative to apps/tg-bot/src/tg_bot/templates/)
templates = Jinja2Templates(
    directory=str(pathlib.Path(__file__).parent.parent / "templates")
)


def _get_service_hub_url(manager: ManagerDep) -> str:
    """Return configured service-hub URL or raise HTTP 503."""
    url = manager.bootstrap.service_hub_url
    if not url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service-hub URL is not configured",
        )
    return url.rstrip("/")


def _bot_config_to_env() -> str:
    """Convert local bot settings to compose.env format."""
    try:
        config = BotSettings.load(_DEFAULT_CONFIG_PATH)
    except Exception:
        config = BotSettings.model_construct()

    lines = [
        "",
        "# ──────────────────────────────────────────────────",
        "# Telegram Bot Config (Gateway)",
        "# ──────────────────────────────────────────────────",
        f"TELEGRAM_ALLOWED_CHAT_IDS={json.dumps(config.allowed_chat_ids)}",
        f"TELEGRAM_ADMIN_CONTACT={config.admin_contact}",
        f"BOT_APP_NAME={config.app_name}",
        f"BOT_BRANCHES={json.dumps(config.branches)}",
        f"BOT_WEBAPP_URL={config.webapp_url}",
        f"BOT_WEBAPP_SHORT_NAME={config.webapp_short_name}",
        f"PROJECT_GITHUB_URL={config.github_url}",
        f"BOT_SERVICE_URL={config.bot_service_url}",
        f"BOT_BUILD_MANAGER_URL={config.build_manager_url}",
        f"BOT_FILE_MANAGER_URL={config.file_manager_url}",
    ]
    return "\n".join(lines)


# ─── Auth Protected Routes ───────────────────────────────────────────

@router.get("/config/schema", dependencies=[Depends(verify_admin_auth)])
async def get_schema(manager: ManagerDep) -> dict[str, Any]:
    """Aggregate schemas from local bot settings and remote service-hub."""
    bot_schema = get_frontend_schema(
        BotSettings,
        title="Telegram Bot Configuration",
        description=(
            "Configures the Telegram bot interface. You need a Bot Token from"
            " @BotFather. You must also specify which chat IDs are allowed to"
            " use the bot to prevent unauthorized access."
        ),
    )

    result = {"bot": bot_schema}

    # Fetch remaining schemas from service-hub
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{service_hub_url}/api/config/schema")
            resp.raise_for_status()
            hub_schemas = resp.json()
            result["agent"] = hub_schemas.get("agent-control", {})
            result["builds"] = hub_schemas.get("build-manager", {})
            result["file_manager"] = hub_schemas.get("file-manager", {})
    except Exception:
        logger.exception("Failed to fetch schemas from service-hub")
        # Soft-fail to keep UI working
        result["agent"] = {"title": "Jenkins Agent", "description": "Offline", "fields": []}
        result["builds"] = {"title": "Build Manager", "description": "Offline", "fields": []}
        result["file_manager"] = {"title": "File Manager", "description": "Offline", "fields": []}

    return result


@router.get("/config", dependencies=[Depends(verify_admin_auth)])
async def get_config(manager: ManagerDep) -> dict[str, Any]:
    """Aggregate config values from local bot config and remote service-hub."""
    bot_config = read_masked_config(BotSettings, _DEFAULT_CONFIG_PATH)

    result = {
        "bot": {
            "values": bot_config.get("values", {}),
            "secret_lengths": bot_config.get("secret_lengths", {}),
        }
    }

    # Fetch from service-hub
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{service_hub_url}/api/config")
            resp.raise_for_status()
            hub_configs = resp.json()
            result["agent"] = hub_configs.get("agent-control", {"values": {}, "secret_lengths": {}})
            result["builds"] = hub_configs.get("build-manager", {"values": {}, "secret_lengths": {}})
            result["file_manager"] = hub_configs.get("file-manager", {"values": {}, "secret_lengths": {}})
    except Exception:
        logger.exception("Failed to fetch config values from service-hub")
        result["agent"] = {"values": {}, "secret_lengths": {}}
        result["builds"] = {"values": {}, "secret_lengths": {}}
        result["file_manager"] = {"values": {}, "secret_lengths": {}}

    return result


@router.put("/config/{scope}", dependencies=[Depends(verify_admin_auth)])
async def save_config(
    scope: str, manager: ManagerDep, request: Request
) -> dict[str, Any]:
    """Save config for a scope. Local for 'bot', proxied for others."""
    incoming = await request.json()

    if scope == "bot":
        save_config_with_merge(BotSettings, _DEFAULT_CONFIG_PATH, incoming)
        # Restart bot dynamically with new settings
        await manager.restart()
        return {"status": "ok", "scope": "bot"}

    # Translate scope for service-hub
    translated = _SCOPE_MAP.get(scope)
    if not translated:
        raise HTTPException(status_code=404, detail=f"Unknown scope: {scope}")

    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(f"{service_hub_url}/api/config/{translated}", json=incoming)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"service-hub error: {exc}")


@router.get("/services/status", dependencies=[Depends(verify_admin_auth)])
async def get_service_status(manager: ManagerDep) -> dict[str, Any]:
    """Aggregate bot manager status and remote service-hub statuses."""
    bot_status = manager.status()

    result = {"bot": bot_status}

    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{service_hub_url}/api/services/status")
            resp.raise_for_status()
            hub_statuses = resp.json()
            result["agent"] = hub_statuses.get("agent-control")
            result["builds"] = hub_statuses.get("build-manager")
            result["file_manager"] = hub_statuses.get("file-manager")
    except Exception:
        logger.exception("Failed to fetch statuses from service-hub")
        offline = {"configured": False, "running": False, "last_error": "Offline"}
        result["agent"] = offline
        result["builds"] = offline
        result["file_manager"] = offline

    return result


@router.post("/services/{scope}/{action}", dependencies=[Depends(verify_admin_auth)])
async def control_service(
    scope: str, action: str, manager: ManagerDep
) -> dict[str, Any]:
    """Control service lifecycle (start/stop/restart). Local for 'bot', proxied for others."""
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    if scope == "bot":
        if action == "start":
            await manager.start()
        elif action == "stop":
            await manager.stop()
        elif action == "restart":
            await manager.restart()
        return manager.status()

    translated = _SCOPE_MAP.get(scope)
    if not translated:
        raise HTTPException(status_code=404, detail=f"Unknown scope: {scope}")

    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{service_hub_url}/api/services/{translated}/{action}")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"service-hub error: {exc}")


@router.get("/services/{scope}/logs", dependencies=[Depends(verify_admin_auth)])
async def get_logs(scope: str, manager: ManagerDep) -> dict[str, Any]:
    """Fetch logs from local buffer for 'bot', proxied for others."""
    if scope == "bot":
        return {"lines": get_buffer_logs()}

    translated = _SCOPE_MAP.get(scope)
    if not translated:
        raise HTTPException(status_code=404, detail=f"Unknown scope: {scope}")

    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{service_hub_url}/api/services/{translated}/logs")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"service-hub error: {exc}")


# ─── Drive OAuth & Connect Proxies ───────────────────────────────────

@router.get("/drive/status", dependencies=[Depends(verify_admin_auth)])
async def get_drive_status(manager: ManagerDep) -> dict[str, Any]:
    """Proxy Drive status query to service-hub."""
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{service_hub_url}/api/drive/status")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/drive/connect/start", dependencies=[Depends(verify_admin_auth)])
async def start_drive_connect(manager: ManagerDep, request: Request) -> dict[str, Any]:
    """Proxy Drive OAuth connect start to service-hub."""
    incoming = await request.json()
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{service_hub_url}/api/drive/connect/start", json=incoming)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.delete("/drive/token", dependencies=[Depends(verify_admin_auth)])
async def disconnect_drive(manager: ManagerDep) -> dict[str, Any]:
    """Proxy Drive token disconnect to service-hub."""
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(f"{service_hub_url}/api/drive/token")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ─── Jenkinsfile & Version ───────────────────────────────────────────

@router.get("/jenkinsfile", dependencies=[Depends(verify_admin_auth)])
async def get_jenkinsfile(
    manager: ManagerDep,
    discard_builds: bool = True,
    clean_workspace: bool = False,
    shallow_clone: bool = True,
    repo_url: str | None = None,
    credentials_id: str | None = None,
) -> dict[str, Any]:
    """Proxy Jenkinsfile aggregation to service-hub."""
    service_hub_url = _get_service_hub_url(manager)
    params: dict[str, Any] = {
        "discard_builds": discard_builds,
        "clean_workspace": clean_workspace,
        "shallow_clone": shallow_clone,
    }
    if repo_url:
        params["repo_url"] = repo_url
    if credentials_id:
        params["credentials_id"] = credentials_id

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{service_hub_url}/api/jenkinsfile", params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/version", dependencies=[Depends(verify_admin_auth)])
async def get_version(manager: ManagerDep) -> dict[str, Any]:
    """Proxy version status check to service-hub."""
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{service_hub_url}/api/version")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ─── Config Transfer (Export / Import) ───────────────────────────────

@router.get("/export/env", dependencies=[Depends(verify_admin_auth)])
async def export_env(manager: ManagerDep) -> dict[str, Any]:
    """Proxy compose.env generation to service-hub and append bot settings."""
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{service_hub_url}/api/export/env")
            resp.raise_for_status()
            data = resp.json()
            compose_env_str = data.get("compose_env", "")
            compose_env_str += _bot_config_to_env()
            data["compose_env"] = compose_env_str
            return data
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/export/tarball", dependencies=[Depends(verify_admin_auth)], response_model=None)
async def export_tarball(manager: ManagerDep) -> Response:
    """Download a .tar.gz containing all config files including local bot.json."""
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{service_hub_url}/api/export/tarball")
            resp.raise_for_status()
            tarball_bytes = resp.content
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch tarball from service-hub: {exc}")

    # Unpack, modify compose.env and add data/bot.json
    in_file = io.BytesIO(tarball_bytes)
    out_file = io.BytesIO()
    with tarfile.open(fileobj=in_file, mode="r:gz") as tar_in:
        with tarfile.open(fileobj=out_file, mode="w:gz") as tar_out:
            for member in tar_in.getmembers():
                f = tar_in.extractfile(member)
                if f is not None:
                    content = f.read()
                    if member.name == "compose.env":
                        bot_env = _bot_config_to_env().encode("utf-8")
                        content = content + bot_env

                    tarinfo = tarfile.TarInfo(name=member.name)
                    tarinfo.size = len(content)
                    tar_out.addfile(tarinfo, io.BytesIO(content))

            # Add data/bot.json
            try:
                bot_json_content = _DEFAULT_CONFIG_PATH.read_bytes()
            except Exception:
                bot_json_content = b"{}"
            tarinfo = tarfile.TarInfo(name="data/bot.json")
            tarinfo.size = len(bot_json_content)
            tar_out.addfile(tarinfo, io.BytesIO(bot_json_content))

    return Response(
        content=out_file.getvalue(),
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=jfb-config.tar.gz"},
    )


@router.post("/import/tarball", dependencies=[Depends(verify_admin_auth)])
async def import_config_tarball(
    manager: ManagerDep,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Import infrastructure state tarball, saving bot.json locally and proxying the rest."""
    raw = await file.read()

    # Extract data/bot.json locally
    bot_imported = False
    in_file = io.BytesIO(raw)
    try:
        with tarfile.open(fileobj=in_file, mode="r:gz") as tar:
            try:
                bot_member = tar.getmember("data/bot.json")
                f = tar.extractfile(bot_member)
                if f is not None:
                    bot_json_content = f.read()
                    _DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                    _DEFAULT_CONFIG_PATH.write_bytes(bot_json_content)
                    bot_imported = True
                    logger.info("Imported bot.json from tarball")
            except KeyError:
                pass  # bot.json not in tarball
    except Exception:
        logger.exception("Failed to extract bot.json from imported tarball")

    # Forward tarball to service-hub
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            files = {"file": (file.filename or "jfb-config.tar.gz", raw, "application/gzip")}
            resp = await client.post(f"{service_hub_url}/api/import/tarball", files=files)
            resp.raise_for_status()
            hub_result = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"service-hub import error: {exc}")

    # Dynamic restart if local bot config was updated
    scopes = hub_result.get("scopes_updated", [])
    if bot_imported:
        scopes = ["bot"] + scopes
        await manager.restart()

    return {
        "status": "ok",
        "scopes_updated": scopes,
        "errors": hub_result.get("errors", []),
    }



# ─── VPN Proxy Endpoints ─────────────────────────────────────────────

@router.post("/services/agent/vpn/upload", dependencies=[Depends(verify_admin_auth)])
async def proxy_vpn_upload(
    manager: ManagerDep, file: UploadFile = File(...)
) -> dict[str, Any]:
    """Proxy multipart .ovpn configuration file upload to service-hub."""
    content = await file.read()
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            files = {"file": (file.filename or "client.ovpn", content, "application/octet-stream")}
            resp = await client.post(f"{service_hub_url}/api/services/agent-control/vpn/upload", files=files)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"service-hub error: {exc}")


@router.get("/services/agent/vpn/status", dependencies=[Depends(verify_admin_auth)])
async def proxy_vpn_status(manager: ManagerDep) -> dict[str, Any]:
    """Proxy VPN status request to service-hub."""
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{service_hub_url}/api/services/agent-control/vpn/status")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.delete("/services/agent/vpn/upload", dependencies=[Depends(verify_admin_auth)])
async def proxy_vpn_delete(manager: ManagerDep) -> dict[str, Any]:
    """Proxy VPN config deletion to service-hub."""
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(f"{service_hub_url}/api/services/agent-control/vpn/upload")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/services/agent/vpn/connect", dependencies=[Depends(verify_admin_auth)])
async def proxy_vpn_connect(manager: ManagerDep) -> dict[str, Any]:
    """Proxy VPN connect request to service-hub."""
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{service_hub_url}/api/services/agent-control/vpn/connect")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/services/agent/vpn/disconnect", dependencies=[Depends(verify_admin_auth)])
async def proxy_vpn_disconnect(manager: ManagerDep) -> dict[str, Any]:
    """Proxy VPN disconnect request to service-hub."""
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{service_hub_url}/api/services/agent-control/vpn/disconnect")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ─── Public OAuth Callback ───────────────────────────────────────────


@router.get("/drive/oauth/callback", name="drive_oauth_callback")
async def drive_oauth_callback(request: Request, manager: ManagerDep) -> HTMLResponse:
    """Handle Google Drive OAuth callback by exchanging code and rendering completion HTML."""
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
                    {
                        "type": "drive-oauth-complete",
                        "success": False,
                        "message": message,
                    }
                ),
            },
            status_code=400,
        )

    # Perform token exchange via service-hub
    service_hub_url = _get_service_hub_url(manager)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{service_hub_url}/api/drive/connect/exchange",
                json={"authorization_response": str(request.url)},
            )
            resp.raise_for_status()
    except Exception as exc:
        msg = f"OAuth exchange failed: {exc}"
        logger.exception("Drive OAuth callback exchange failed")
        return templates.TemplateResponse(
            request=request,
            name="oauth_callback.html",
            context={
                "title": "Google Drive Connection Failed",
                "message": msg,
                "payload_json": json.dumps(
                    {
                        "type": "drive-oauth-complete",
                        "success": False,
                        "message": msg,
                    }
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
                {
                    "type": "drive-oauth-complete",
                    "success": True,
                    "message": message,
                }
            ),
        },
    )
