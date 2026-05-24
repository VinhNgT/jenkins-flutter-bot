"""Telegram Web App API endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..dependencies import ManagerDep
from ..bot.store import ActiveBuild

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
    x_telegram_init_data: str = Header(...),
) -> WebAppUser:
    """Validate initData and check chat authorization."""
    ctx = manager.bot_context
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot service is not running",
        )

    # Allow preview mode bypass only in development / testing environments
    if x_telegram_init_data == "preview":
        is_dev = (
            os.environ.get("JFB_DEV_MODE") == "true"
            or ctx.config.telegram_token in ("123456:test-token", "fake:token", "")
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
        chat_id = ctx.config.allowed_chat_ids[0]
        return WebAppUser(
            chat_id=chat_id,
            user_id=12345,
            first_name="Preview",
            username="preview_user",
        )

    try:
        data = _verify_telegram_init_data(x_telegram_init_data, ctx.config.telegram_token)
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
    chat_id = None
    chat_data = data.get("chat")
    start_param = data.get("start_param")

    if chat_data and "id" in chat_data:
        if chat_data.get("type") == "private":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Private chats are disabled. Please use an authorized group.",
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
            detail="Private chats are disabled. Please use an authorized group.",
        )

    if chat_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Private chats are disabled. Please use an authorized group.",
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
            detail=f"Chat ID {chat_id} is not authorized",
        )

    return WebAppUser(
        chat_id=chat_id,
        user_id=user_data.get("id", 0),
        first_name=user_data.get("first_name", "User"),
        username=user_data.get("username"),
    )


ValidatedUser = Annotated[WebAppUser, Depends(validate_webapp_request)]


@router.get("/config")
async def get_webapp_config(
    manager: ManagerDep,
    user: ValidatedUser,
) -> dict:
    """Return configuration and active builds for the web app."""
    ctx = manager.bot_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    # Map our bot config branches
    branches_list = []
    for label, ref in ctx.config.branches.items():
        branches_list.append({"label": label, "ref": ref})

    # Get active builds formatted for frontend
    active_builds = []
    for build in ctx.list_building():
        active_builds.append({
            "request_id": build.request_id,
            "label": build.label,
            "ref": build.ref,
            "triggered_at": build.triggered_at,
            "triggered_by": build.triggered_by,
        })

    return {
        "app_name": ctx.config.app_name,
        "branches": branches_list,
        "active_builds": active_builds,
    }


@router.post("/trigger")
async def trigger_webapp_build(
    manager: ManagerDep,
    user: ValidatedUser,
    req: TriggerRequest,
) -> dict:
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
    msg_text = f"🔨 <b>{triggered_by} started a {label} build</b>"
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
    )

    return {"ok": True, "request_id": request_id}


@router.post("/cancel")
async def cancel_webapp_build(
    manager: ManagerDep,
    user: ValidatedUser,
    req: CancelRequest,
) -> dict:
    """Cancel an active build from the Web App."""
    ctx = manager.bot_context
    if ctx is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    # 1. Verify it exists
    build = ctx.store.consume(req.request_id)
    if not build:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Build not found or already completed",
        )

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
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Build cancellation failed: {e}",
        )

    return {"ok": True}
