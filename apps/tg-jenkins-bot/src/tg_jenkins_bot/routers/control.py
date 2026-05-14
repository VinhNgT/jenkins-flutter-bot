"""Control routes — /control/*."""

from __future__ import annotations

from typing import Any

from config_core import get_frontend_schema, read_masked_config, save_config_with_merge
from fastapi import APIRouter, HTTPException, Request

from ..config import BotConfig, _DEFAULT_CONFIG_PATH
from ..dependencies import ManagerDep

router = APIRouter(prefix="/control", tags=["control"])


@router.post("/start")
async def start_bot(manager: ManagerDep) -> dict[str, Any]:
    """Start the Telegram bot if it is not already running."""
    try:
        await manager.start()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


@router.post("/stop")
async def stop_bot(manager: ManagerDep) -> dict[str, Any]:
    """Stop the Telegram bot if it is running."""
    await manager.stop()
    return manager.status()


@router.post("/restart")
async def restart_bot(manager: ManagerDep) -> dict[str, Any]:
    """Restart the Telegram bot using the current resolved config."""
    try:
        await manager.restart()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


@router.get("/status")
async def bot_status(manager: ManagerDep) -> dict[str, Any]:
    """Report whether the Telegram bot is configured and running."""
    return manager.status()


@router.get("/schema")
async def get_schema() -> dict[str, Any]:
    """Return the bot module's config field schema."""
    return get_frontend_schema(
        BotConfig,
        title="Telegram Bot Configuration",
        description=(
            "Configures the Telegram bot interface. You need a Bot Token from"
            " @BotFather. You must also specify which chat IDs are allowed to"
            " use the bot to prevent unauthorized access."
        )
    )


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """Return current config values with secrets masked."""
    return read_masked_config(BotConfig, _DEFAULT_CONFIG_PATH)


@router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    payload = await request.json()
    save_config_with_merge(BotConfig, _DEFAULT_CONFIG_PATH, payload)
    return {"status": "saved"}
