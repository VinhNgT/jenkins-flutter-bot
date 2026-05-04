"""Webhook routes — receive build results from Jenkins."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

if TYPE_CHECKING:
    from ..bot.context import BotContext

logger = logging.getLogger(__name__)

WORK_DIR = Path("data/work")

webhook_router = APIRouter(tags=["webhook"])


def _get_bot_context(request: Request) -> BotContext | None:
    manager = request.app.state.manager
    return manager.bot_context


@webhook_router.get("/health")
async def handle_health(request: Request) -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "OK"}


@webhook_router.post("/webhook/build-complete")
async def handle_build_complete(
    request: Request,
    metadata: str = Form(),
    artifact: UploadFile | None = File(default=None),
) -> dict[str, str]:
    """Handle Jenkins build completion callback.

    Expected multipart POST:
            - Field 'metadata': JSON with request_id, status, commit_hash, logs
      - Field 'artifact': The built APK file (only on success)

    Validation order: metadata is parsed and request_id/job_id are
    validated *before* the artifact is written to disk.  This avoids
    unnecessary disk I/O for invalid requests.
    """
    ctx = _get_bot_context(request)
    if ctx is None:
        raise HTTPException(status_code=503, detail="Bot is not running")

    # ------------------------------------------------------------------
    # 1. Parse and validate metadata BEFORE writing artifact to disk
    # ------------------------------------------------------------------
    metadata_obj = json.loads(metadata)
    request_id = metadata_obj.get("request_id")
    job_id = metadata_obj.get("job_id")
    status = metadata_obj.get("status", "unknown")
    commit_hash = metadata_obj.get("commit_hash", "unknown")

    # Truncate request_id in logs to prevent token leakage
    short_rid = request_id[:8] if request_id else "none"

    logger.info(
        "Build callback: request_id=%s…, job_id=%s, status=%s, commit=%s",
        short_rid,
        job_id,
        status,
        commit_hash,
    )

    # Reject mismatched job_id early — no artifact written
    if job_id and job_id != ctx.config.jenkins_job_id:
        logger.info(
            "Ignoring callback for job_id=%s (expected %s)",
            job_id,
            ctx.config.jenkins_job_id,
        )
        return {"status": "ignored", "reason": "different job_id"}

    # Consume pending build — returns None if not triggered via Telegram
    pending = ctx.consume_pending(request_id)

    if pending is None:
        logger.info(
            "No pending Telegram request for request_id=%s… — ignoring.",
            short_rid,
        )
        return {"status": "ignored", "reason": "not triggered by bot"}

    # ------------------------------------------------------------------
    # 2. Only write artifact to disk after validation passes
    # ------------------------------------------------------------------
    artifact_path = None
    if artifact is not None:
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".apk", dir=str(WORK_DIR)
        )
        while True:
            chunk = await artifact.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
        tmp.close()
        artifact_path = tmp.name

    # ------------------------------------------------------------------
    # 3. Process the validated, Telegram-triggered build result
    # ------------------------------------------------------------------
    if status == "success" and artifact_path:
        await ctx.on_build_success(pending, metadata_obj, artifact_path)
    else:
        await ctx.on_build_failure(pending, metadata_obj)
        if artifact_path:
            Path(artifact_path).unlink(missing_ok=True)

    return {"status": "ok"}
