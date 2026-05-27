"""Telegram Web App API endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib.metadata
import json
import logging
import os
import re
import time
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from ..dependencies import ManagerDep

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


class WebAppConfigResponse(BaseModel):
    """GET /api/webapp/config response."""

    app_name: str
    app_version: str
    branches: list[BranchItem]
    active_builds: list[ActiveBuildResponse]


class RecentBuildItem(BaseModel):
    """A completed build from history."""

    branch: str
    label: str | None = None
    commit_hash: str | None
    result: str
    triggered_at: float
    completed_at: float
    download_url: str | None


class RecentBuildsResponse(BaseModel):
    """GET /api/webapp/recent response."""

    builds: list[RecentBuildItem]


class TriggerResponse(BaseModel):
    """POST /api/webapp/trigger response."""

    ok: bool = True
    request_id: str


class CancelResponse(BaseModel):
    """POST /api/webapp/cancel response."""

    ok: bool = True


def _verify_telegram_init_data(init_data: str, token: str) -> dict:
    """Verify Telegram initData signature and return parsed data.

    Raises ValueError if signature is invalid.
    """
    # Parse query parameters
    params = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    params_dict = dict(params)

    if "hash" not in params_dict:
        raise ValueError("Missing hash parameter")

    received_hash = params_dict.pop("hash")

    # Sort key-value pairs alphabetically
    sorted_params = sorted(params_dict.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)

    # Calculate secret key: HMAC-SHA256 of token with constant key "WebAppData"
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()

    # Calculate HMAC-SHA256 of data_check_string using secret_key
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid hash signature")

    # Replay protection: reject initData older than 1 hour.
    # The HMAC proves authenticity but never expires. Without this check,
    # a captured initData (from browser history, DevTools, or SSE query
    # parameter) could be replayed indefinitely. Telegram's own documentation
    # recommends checking auth_date. The 1-hour window balances security
    # against clock skew and normal user session lengths.
    _INIT_DATA_TTL = 3600  # 1 hour
    auth_date_str = params_dict.get("auth_date")
    if auth_date_str:
        try:
            auth_date = int(auth_date_str)
            if time.time() - auth_date > _INIT_DATA_TTL:
                raise ValueError("initData expired (auth_date too old)")
        except ValueError:
            raise
        except (TypeError, OverflowError):
            pass

    # Parse nested JSON structures
    result = {}
    for k, v in params_dict.items():
        try:
            result[k] = json.loads(v)
        except json.JSONDecodeError:
            result[k] = v

    return result


async def validate_webapp_request(
    manager: ManagerDep,
    x_telegram_init_data: str | None = Header(None),
    init_data: str | None = Query(None),
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

    # Allow preview mode bypass only in development / testing environments
    if init_data_str == "preview":
        is_dev = os.environ.get(
            "JFB_DEV_MODE"
        ) == "true" or ctx.config.telegram_token in (
            "123456:test-token",
            "fake:token",
            "",
        )
        if not is_dev:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Preview mode is not allowed in production",
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
        data = _verify_telegram_init_data(init_data_str, ctx.config.telegram_token)
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
    """Return configuration and active builds for the web app."""
    ctx = manager.bot_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    # Map our bot config branches
    branches_list = []
    for label, ref in ctx.config.branches.items():
        branches_list.append(BranchItem(label=label, ref=ref))

    # Get active builds formatted for frontend
    active_builds = []
    for build in ctx.list_building():
        active_builds.append(
            ActiveBuildResponse(
                request_id=build.request_id,
                label=build.label,
                ref=build.ref,
                triggered_at=build.triggered_at,
                triggered_by=build.triggered_by,
                triggered_by_id=build.triggered_by_id,
            )
        )

    try:
        v = importlib.metadata.version("tg-jenkins-bot")
        v = re.sub(r"^(\d+\.\d+\.\d+)\.(dev|rc)(\d+)$", r"\1-\2.\3", v)
    except importlib.metadata.PackageNotFoundError:
        v = "unknown"

    return WebAppConfigResponse(
        app_name=ctx.config.app_name,
        app_version=v,
        branches=branches_list,
        active_builds=active_builds,
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

    event = asyncio.Event()
    ctx.store.add_listener(event)
    last_sent_hash = None

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected")
                break

            active_builds = []
            for build in ctx.list_building():
                active_builds.append(
                    {
                        "request_id": build.request_id,
                        "label": build.label,
                        "ref": build.ref,
                        "triggered_at": build.triggered_at,
                        "triggered_by": build.triggered_by,
                        "triggered_by_id": build.triggered_by_id,
                    }
                )

            # Only stream updates down the wire when the builds state actually mutates.
            # Hash the canonical JSON for deduplication, but pass the raw list to
            # ServerSentEvent — FastAPI serializes `data` automatically.
            current_str = json.dumps(active_builds, sort_keys=True)
            current_hash = hashlib.sha256(current_str.encode()).hexdigest()

            if last_sent_hash is None or current_hash != last_sent_hash:
                last_sent_hash = current_hash
                yield ServerSentEvent(data=active_builds, event="builds")

            # Wait until store mutation sets the event, or timeout (15s) for a keep-alive window.
            try:
                await asyncio.wait_for(event.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                pass

            event.clear()
    except asyncio.CancelledError:
        logger.info("SSE streaming cancelled")
        raise
    finally:
        ctx.store.remove_listener(event)



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

    # 1. Duplicate detection
    existing = ctx.store.find_by_branch(req.branch)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A build on branch '{req.branch}' is already in progress.",
        )

    # 2. Match label
    label = req.branch
    for k, v in ctx.config.branches.items():
        if v == req.branch:
            label = k
            break

    # 3. Call build-manager
    try:
        res = await ctx.build_client.trigger_build(
            branch=req.branch,
            callback_url=ctx.config.bot_callback_url,
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

    # 4. Notify Telegram chat
    triggered_by = user.first_name
    msg_text = (
        f"🔨 <b>{triggered_by} started a {label} build</b>\n"
        f"📦 Branch: <code>{req.branch}</code>"
    )
    if ctx.bot:
        try:
            await ctx.bot.send_message(
                chat_id=user.chat_id,
                text=msg_text,
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Failed to send trigger message to Telegram")

    # 5. Register in store
    ctx.store.register(
        request_id=request_id,
        chat_id=user.chat_id,
        ref=req.branch,
        label=label,
        triggered_by=triggered_by,
        triggered_by_id=user.user_id,
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

    # 1. Verify it exists
    build = ctx.store.get(req.request_id)
    if not build:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Build not found or already completed",
        )

    # Enforce: Only the user who triggered the build can cancel it
    if build.triggered_by_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the user who triggered the build can cancel it.",
        )

    # Consume/remove from active store since the user is authorized to cancel it
    ctx.store.consume(req.request_id)

    # 2. Call build-manager to cancel
    try:
        await ctx.build_client.cancel_build(req.request_id)
    except Exception as e:
        logger.exception("Failed to cancel build via build-manager")
        # Put back in store since cancel failed
        ctx.store.register(
            request_id=build.request_id,
            chat_id=build.chat_id,
            ref=build.ref,
            label=build.label,
            triggered_by=build.triggered_by,
            triggered_by_id=build.triggered_by_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Build cancellation failed: {e}",
        )

    # 3. Send Telegram notification to the group chat showing who cancelled it
    try:
        await ctx.on_build_cancelled(build, user.first_name)
    except Exception:
        logger.exception("Failed to send cancellation message to Telegram")

    return CancelResponse()


@router.get("/recent", response_model=RecentBuildsResponse)
async def get_recent_builds(
    manager: ManagerDep,
    user: ValidatedUser,
) -> RecentBuildsResponse:
    """Return recent completed builds for the web app."""
    ctx = manager.bot_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    branches_map = {v: k for k, v in ctx.config.branches.items()}

    builds = await ctx.build_client.get_recent_builds(count=5)
    return RecentBuildsResponse(
        builds=[
            RecentBuildItem(
                branch=b.branch,
                label=branches_map.get(b.branch, b.branch),
                commit_hash=b.commit_hash,
                result=b.result,
                triggered_at=b.triggered_at,
                completed_at=b.completed_at,
                download_url=b.download_url,
            )
            for b in builds
        ]
    )

