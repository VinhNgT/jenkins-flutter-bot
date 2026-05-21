"""Admin bot lifecycle management.

Mirrors ``BotManager`` from ``tg-jenkins-bot`` — manages Telegram
polling startup and shutdown behind a FastAPI lifespan.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic import ValidationError
from telegram.ext import Application

from .client import HubClient
from .config import AdminBotBootstrap
from .handlers import register_handlers

logger = logging.getLogger(__name__)


class StartupError(Exception):
    """Raised when the admin bot manager fails to start."""


class AdminBotManager:
    """Manage admin bot startup, shutdown, and status."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._application: Application | None = None  # type: ignore[type-arg]
        self._hub_client: HubClient | None = None
        self._last_error: str | None = None
        self._started_at: float | None = None

    @property
    def running(self) -> bool:
        return self._application is not None

    async def start(self) -> None:
        """Resolve config, build Telegram Application, start polling."""
        async with self._lock:
            if self.running:
                return

            try:
                config = AdminBotBootstrap.load()
            except (ValueError, ValidationError) as e:
                self._last_error = str(e)
                raise StartupError(str(e)) from e

            try:
                hub_client = HubClient(config.config_hub_url)
                application = Application.builder().token(config.bot_token).build()

                # Wire shared state into bot_data
                application.bot_data["config"] = config
                application.bot_data["hub_client"] = hub_client

                register_handlers(application)

                await application.initialize()
                await application.start()
                if not application.updater:
                    raise RuntimeError("Application.updater is None after start")
                await application.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=["message", "callback_query"],
                )

                # Register visible commands
                await application.bot.set_my_commands(
                    [("admin", "Admin control panel")]
                )

                self._application = application
                self._hub_client = hub_client
                self._last_error = None
                self._started_at = time.time()
                logger.info(
                    "Admin bot started (chat_id=%d)", config.admin_chat_id
                )
            except Exception as exc:
                self._last_error = str(exc)
                raise StartupError(str(exc)) from exc

    async def stop(self) -> None:
        """Gracefully stop the Telegram polling application."""
        async with self._lock:
            if not self._application:
                return

            application = self._application
            logger.info("Stopping admin bot...")
            if application.updater:
                await application.updater.stop()
            await application.stop()
            await application.shutdown()

            if self._hub_client:
                await self._hub_client.close()

            self._application = None
            self._hub_client = None
            self._started_at = None

    async def restart(self) -> None:
        """Restart the admin bot with fresh config."""
        await self.stop()
        await self.start()

    def status(self) -> dict[str, Any]:
        """Return the current admin bot manager status."""
        config_error: str | None = None
        try:
            AdminBotBootstrap.load()
        except Exception as exc:
            from config_core import format_validation_error

            config_error = format_validation_error(exc)
        result: dict[str, Any] = {
            "configured": config_error is None,
            "running": self.running,
            "last_error": self._last_error,
            "config_error": config_error,
        }
        if self._started_at is not None:
            result["started_at"] = self._started_at
        return result
