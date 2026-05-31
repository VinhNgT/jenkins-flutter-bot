"""Telegram Web App API endpoints."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import re
from typing import Annotated

import httpx

from ..telegram import verify_init_data
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from ..dependencies import ManagerDep
from ..build_client import BuildClientError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webapp", tags=["webapp"])


class WebAppUser(BaseModel):
    """Authenticated user info parsed from Telegram initData."""

    chat_id: int
    user_id: int
    first_name: str
    username: str | None = None


class TriggerRequest(BaseModel):
    """Request payload to trigger a build."""

    branch: str
    notify: bool = True


class CancelRequest(BaseModel):
    """Request payload to cancel a build."""

    request_id: str


# ── Response Models ──────────────────────────────────────────────


class BranchItem(BaseModel):
    """A configured branch option."""

    label: str
    ref: str


class ActiveBuildResponse(BaseModel):
    """An active build currently in progress."""

    request_id: str
    label: str
    ref: str
    triggered_at: float
    triggered_by: str
    triggered_by_id: int
    estimated_duration: int = 0


class WebAppConfigResponse(BaseModel):
    """GET /api/webapp/config response."""

    app_name: str
    app_version: str
    branches: list[BranchItem]



class RecentBuildItem(BaseModel):
    """A completed build from history."""

    request_id: str
    branch: str
    label: str | None = None
    commit_hash: str | None
    result: str
    triggered_at: float
    completed_at: float
    download_url: str | None
    file_size: int = 0
    build_number: int = 0



class TriggerResponse(BaseModel):
    """POST /api/webapp/trigger response."""

    ok: bool = True
    request_id: str


class CancelResponse(BaseModel):
    """POST /api/webapp/cancel response."""

    ok: bool = True





security = HTTPBasic(auto_error=False)


async def validate_webapp_request(
    manager: ManagerDep,
    x_telegram_init_data: str | None = Header(None),
    init_data: str | None = Query(None),
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> WebAppUser:
    """Validate initData and check chat authorization."""
    ctx = manager.bot_context
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot service is not running",
        )

    # Fall back to query param if header is missing
    init_data_str = x_telegram_init_data or init_data
    if not init_data_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Telegram authentication credentials",
        )

    # Validate preview mode requests using configured Basic Auth credentials
    if init_data_str == "preview":
        enable_preview = manager.bootstrap.enable_browser_preview
        if not enable_preview:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Browser preview is disabled in production",
            )

        # Require Basic Auth
        username = manager.bootstrap.browser_auth_username
        password = manager.bootstrap.browser_auth_password

        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Browser preview authentication credentials not configured on backend",
            )

        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Basic"},
            )

        is_correct_username = secrets.compare_digest(credentials.username, username)
        is_correct_password = secrets.compare_digest(credentials.password, password)

        if not (is_correct_username and is_correct_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Basic"},
            )

        if not ctx.config.allowed_chat_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No allowed chats configured",
            )
        return WebAppUser(
            chat_id=ctx.config.allowed_chat_ids[0],
            user_id=12345,
            first_name="Preview",
            username="preview_user",
        )

    try:
        data = verify_init_data(init_data_str, manager.bootstrap.telegram_bot_token)
    except ValueError as e:
        logger.warning("Invalid webapp initData: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e}",
        )

    # Extract user
    user_data = data.get("user")
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing user field in initData",
        )

    # Determine chat ID
    # In groups/channels, chat.id is present. In private, it's user.id.
    # If launched via deep link, chat.id is missing but we pass the chat ID as start_param.
    chat_id: int | None = None
    chat_data = data.get("chat")
    start_param = data.get("start_param")
    bot_username = getattr(ctx.bot, "username", None) if ctx.bot else None

    if chat_data and "id" in chat_data:
        if chat_data.get("type") == "private":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "private_chat_disabled",
                    "message": "Private chats are disabled. Please use an authorized group.",
                    "bot_username": bot_username,
                },
            )
        chat_id = chat_data["id"]
    elif start_param:
        try:
            chat_id = int(start_param)
        except ValueError:
            pass

    # Private chats are disabled (positive chat IDs represent user/private chats)
    if chat_id is not None and chat_id > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "private_chat_disabled",
                "message": "Private chats are disabled. Please use an authorized group.",
                "bot_username": bot_username,
            },
        )

    if chat_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "private_chat_disabled",
                "message": "Private chats are disabled. Please use an authorized group.",
                "bot_username": bot_username,
            },
        )

    # Verify authorization
    if chat_id not in ctx.config.allowed_chat_ids:
        logger.warning(
            "Unauthorized chat ID %d attempted Web App access (user_id=%d)",
            chat_id,
            user_data.get("id", 0),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "group_not_authorized",
                "message": f"Chat ID {chat_id} is not authorized",
                "chat_id": chat_id,
                "bot_username": bot_username,
            },
        )

    return WebAppUser(
        chat_id=chat_id,
        user_id=user_data.get("id", 0),
        first_name=user_data.get("first_name", "User"),
        username=user_data.get("username"),
    )


ValidatedUser = Annotated[WebAppUser, Depends(validate_webapp_request)]


@router.get("/config", response_model=WebAppConfigResponse)
async def get_webapp_config(
    manager: ManagerDep,
    user: ValidatedUser,
) -> WebAppConfigResponse:
    """Return configuration for the web app."""
    ctx = manager.bot_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    # Map our bot config branches
    branches_list = []
    for label, ref in ctx.config.branches.items():
        branches_list.append(BranchItem(label=label, ref=ref))

    try:
        v = importlib.metadata.version("tg-bot")
        v = re.sub(r"^(\d+\.\d+\.\d+)\.(dev|rc)(\d+)$", r"\1-\2.\3", v)
    except importlib.metadata.PackageNotFoundError:
        v = "unknown"

    return WebAppConfigResponse(
        app_name=ctx.config.app_name,
        app_version=v,
        branches=branches_list,
    )


@router.get("/stream", response_class=EventSourceResponse)
async def stream_active_builds(
    request: Request,
    manager: ManagerDep,
    user: ValidatedUser,
):
    """Stream active builds using Server-Sent Events (SSE).

    This is an async generator endpoint.  FastAPI's ``response_class =
    EventSourceResponse`` wraps the yielded ``ServerSentEvent`` objects into a
    proper ``text/event-stream`` response with keep-alive pings, no-cache
    headers, and proxy-buffering prevention — all handled automatically.
    """
    ctx = manager.bot_context
    if ctx is None:
        return

    try:
        async with ctx.build_client.stream_builds() as response:
            if response.status_code != 200:
                logger.error("Failed to connect to build-manager stream: HTTP %d", response.status_code)
                return

            # Buffer for incomplete SSE lines
            event_type = "message"
            data_lines: list[str] = []

            async for line in response.aiter_lines():
                if await request.is_disconnected():
                    break

                if not line:
                    # Empty line signals dispatch of the SSE event
                    if data_lines:
                        data_str = "".join(data_lines)
                        try:
                            payload = json.loads(data_str)
                            # Translate payload!
                            if event_type == "builds":
                                translated = []
                                for b in payload:
                                    ref = b.get("branch", "")
                                    label = b.get("label", ref)
                                    for k, v in ctx.config.branches.items():
                                        if v == ref:
                                            label = k
                                            break
                                    translated.append({
                                        "request_id": b.get("request_id", ""),
                                        "label": label,
                                        "ref": ref,
                                        "triggered_at": b.get("triggered_at", 0.0),
                                        "triggered_by": b.get("triggered_by", ""),
                                        "triggered_by_id": b.get("triggered_by_id", 0),
                                        "estimated_duration": b.get("estimated_duration", 0),
                                    })
                                yield ServerSentEvent(data=translated, event="builds")
                            elif event_type == "recent":
                                branches_map = {v: k for k, v in ctx.config.branches.items()}
                                translated = []
                                for b in payload:
                                    branch = b.get("branch", "")
                                    translated.append({
                                        "request_id": b.get("request_id", ""),
                                        "branch": branch,
                                        "label": branches_map.get(branch, branch),
                                        "commit_hash": b.get("commit_hash", ""),
                                        "result": b.get("result", ""),
                                        "triggered_at": b.get("triggered_at", 0.0),
                                        "completed_at": b.get("completed_at", 0.0),
                                        "download_url": b.get("download_url", ""),
                                        "file_size": b.get("file_size", 0),
                                        "build_number": b.get("build_number", 0),
                                    })
                                yield ServerSentEvent(data=translated, event="recent")
                            else:
                                yield ServerSentEvent(data=payload, event=event_type)
                        except Exception:
                            logger.exception("Failed to parse and translate SSE event from build-manager")

                        data_lines = []
                        event_type = "message"
                    continue

                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())

    except httpx.HTTPError as exc:
        logger.info("Build manager connection closed: %s", exc)
    except asyncio.CancelledError:
        logger.info("SSE proxy generator cancelled")
        raise
    except Exception:
        logger.exception("Error in SSE proxy streaming from build-manager")


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_webapp_build(
    manager: ManagerDep,
    user: ValidatedUser,
    req: TriggerRequest,
) -> TriggerResponse:
    """Trigger a new build from the Web App."""
    ctx = manager.bot_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    label = req.branch
    for k, v in ctx.config.branches.items():
        if v == req.branch:
            label = k
            break

    try:
        res = await ctx.build_client.trigger_build(
            branch=req.branch,
            callback_url=ctx.config.bot_callback_url,
            app_name=ctx.config.app_name,
            label=label,
            triggered_by=user.first_name,
            triggered_by_id=user.user_id,
            notify=req.notify,
            chat_id=user.chat_id,
        )
    except BuildClientError as e:
        if "HTTP 409" in e.args[0]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A build on branch '{req.branch}' is already in progress.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=e.user_message,
        )
    except Exception as e:
        logger.exception("Failed to trigger build via build-manager")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Build server error: {e}",
        )

    request_id = res.get("request_id")
    if not request_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Build manager did not return a request ID",
        )

    return TriggerResponse(request_id=request_id)


@router.post("/cancel", response_model=CancelResponse)
async def cancel_webapp_build(
    manager: ManagerDep,
    user: ValidatedUser,
    req: CancelRequest,
) -> CancelResponse:
    """Cancel an active build from the Web App."""
    ctx = manager.bot_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    # 1. Fetch pending builds from build-manager
    builds = await ctx.build_client.get_pending_builds()
    build = builds.get(req.request_id)
    if not build:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Build not found or already completed",
        )

    # Enforce: Only the user who triggered the build can cancel it
    if build.get("triggered_by_id", 0) != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the user who triggered the build can cancel it.",
        )

    # 2. Call build-manager to cancel
    try:
        await ctx.build_client.cancel_build(req.request_id)
    except Exception as e:
        logger.exception("Failed to cancel build via build-manager")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Build cancellation failed: {e}",
        )

    return CancelResponse()


