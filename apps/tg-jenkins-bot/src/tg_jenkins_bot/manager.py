"""Bot lifecycle management.

The bot is a thin Telegram frontend — all build management is
delegated to the build-manager service via :class:`BuildClient`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from config_core import format_validation_error
from pydantic import ValidationError

from telegram import Bot, MenuButtonDefault
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
)

from .bot.context import BotContext
from .bot.handlers import (
    recent_handler,
    start_handler,
    status_handler,
)
from .build_client import BuildClient
from .config import BotSettings

logger = logging.getLogger(__name__)


class StartupError(Exception):
    """Raised when the bot manager fails to start."""


def _build_application(
    config: BotSettings,
    build_client: BuildClient,
    bot: Bot,
    *,
    clock: Callable[[], float] = time.time,
) -> tuple[Application, BotContext]:
    """Create a Telegram Application wired with the passive handler architecture."""
    application = ApplicationBuilder().bot(bot).build()

    bot_context = BotContext(
        config=config,
        build_client=build_client,
        bot=bot,
        clock=clock,
    )
    application.bot_data["bot_context"] = bot_context

    # Slash commands
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", start_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(CommandHandler("recent", recent_handler))

    return application, bot_context


class BotManager:
    """Manage Telegram bot startup, shutdown, and status."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._lock = asyncio.Lock()
        self._application: Application | None = None
        self._bot_context: BotContext | None = None
        self._config: BotSettings | None = None
        self._build_client: BuildClient | None = None
        self._last_error: str | None = None
        self._started_at: float | None = None
        self._clock = clock

    @property
    def bot_context(self) -> BotContext | None:
        return self._bot_context

    @property
    def running(self) -> bool:
        return self._application is not None and self._bot_context is not None

    async def start(self, config: BotSettings | None = None) -> None:
        """Build and start the Telegram polling application."""
        async with self._lock:
            if self.running:
                return

            try:
                config = config or BotSettings.load()
            except (ValueError, ValidationError) as e:
                self._last_error = str(e)
                raise StartupError(str(e)) from e

            try:
                build_client = BuildClient(config.build_manager_url)
                bot = Bot(config.telegram_token)
                application, bot_context = _build_application(
                    config,
                    build_client,
                    bot,
                    clock=self._clock,
                )

                await application.initialize()
                await application.start()
                if not application.updater:
                    raise RuntimeError("Application.updater is None after start")
                await application.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=["message"],
                )

                # Register visible commands in the "/" picker
                await application.bot.set_my_commands(
                    [
                        ("recent", "Show recent builds"),
                        ("status", "Check build system health"),
                        ("help", "How to use this bot"),
                    ]
                )

                # Ensure the chat menu button is set to default (consistent experience across all chats)
                await application.bot.set_chat_menu_button(
                    menu_button=MenuButtonDefault()
                )

                self._application = application
                self._bot_context = bot_context
                self._config = config
                self._build_client = build_client
                self._last_error = None
                self._started_at = self._clock()
                logger.info("Telegram bot started (Web App mode)")
            except Exception as exc:
                self._last_error = str(exc)
                raise StartupError(str(exc)) from exc

    async def stop(self) -> None:
        """Gracefully stop the Telegram polling application."""
        async with self._lock:
            if not self._application:
                return

            application = self._application
            logger.info("Stopping Telegram bot...")
            if application.updater:
                await application.updater.stop()
            await application.stop()
            await application.shutdown()

            # Close reusable HTTP clients
            if self._build_client:
                await self._build_client.close()

            self._application = None
            self._bot_context = None
            self._config = None
            self._build_client = None
            self._started_at = None

    async def restart(self) -> None:
        """Restart the Telegram polling application."""
        await self.stop()
        await self.start()

    def status(self) -> dict[str, Any]:
        """Return the current bot manager status."""
        config_error: str | None = None
        try:
            BotSettings.load()
        except Exception as exc:
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
