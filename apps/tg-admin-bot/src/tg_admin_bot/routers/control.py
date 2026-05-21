"""Control routes — /control/*.

Standard service lifecycle endpoints matching the pattern used by
all other managed services in the stack.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..dependencies import ManagerDep

router = APIRouter(prefix="/control", tags=["control"])


@router.post("/start")
async def start_bot(manager: ManagerDep) -> dict[str, Any]:
    """Start the admin bot if it is not already running."""
    await manager.start()
    return manager.status()


@router.post("/stop")
async def stop_bot(manager: ManagerDep) -> dict[str, Any]:
    """Stop the admin bot if it is running."""
    await manager.stop()
    return manager.status()


@router.post("/restart")
async def restart_bot(manager: ManagerDep) -> dict[str, Any]:
    """Restart the admin bot using the current resolved config."""
    await manager.restart()
    return manager.status()


@router.get("/status")
async def bot_status(manager: ManagerDep) -> dict[str, Any]:
    """Report whether the admin bot is configured and running."""
    return manager.status()
