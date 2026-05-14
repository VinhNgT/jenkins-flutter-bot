"""Build event callback routes — /callback/*."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from ..dependencies import ManagerDep

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

    pending = ctx.consume_pending(request_id)
    if pending is None:
        logger.info(
            "Build result for unknown request_id=%s — ignoring",
            request_id[:8],
        )
        return {"status": "ignored", "reason": "no pending build"}

    if result == "success":
        await ctx.on_build_success(pending, body)
    else:
        await ctx.on_build_failure(pending, body)

    return {"status": "processed"}
