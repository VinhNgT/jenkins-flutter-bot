"""Build event callback routes — /callback/*."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from ..dependencies import ManagerDep
from ..bot.context import ActiveBuild

logger = logging.getLogger(__name__)

router = APIRouter(tags=["callback"])


@router.post("/callback/build-result")
async def handle_build_result(manager: ManagerDep, request: Request) -> dict[str, str]:
    """Receive a build result forwarded by the build-manager.

    Expected JSON payload::

        {
            "request_id": "abc123",
            "branch": "main",
            "commit_hash": "abc1234",
            "result": "success",
            "triggered_at": 1715500000.0,
            "completed_at": 1715501000.0,
            "download_url": "https://..."
        }
    """
    ctx = manager.bot_context
    if ctx is None:
        return {"status": "ignored", "reason": "bot not running"}

    body = await request.json()
    request_id = body.get("request_id", "")
    result = body.get("result", "")

    chat_id = body.get("chat_id", 0)
    if not chat_id:
        logger.info(
            "Build result for unknown request_id=%s (no chat_id) — ignoring",
            request_id[:8],
        )
        return {"status": "ignored", "reason": "no chat_id"}

    building = ActiveBuild(
        chat_id=chat_id,
        ref=body.get("branch", ""),
        label=body.get("label", body.get("branch", "")),
        request_id=request_id,
        triggered_at=body.get("triggered_at", 0.0),
        triggered_by=body.get("triggered_by", ""),
        triggered_by_id=body.get("triggered_by_id", 0),
        notify=body.get("notify", True),
    )

    if result == "success":
        await ctx.on_build_success(building, body)
    elif result == "timeout":
        await ctx.on_build_timeout(building, body)
    elif result in ("aborted", "cancelled"):
        await ctx.on_build_cancelled(building)
    else:
        await ctx.on_build_failure(building, body)

    return {"status": "processed"}
