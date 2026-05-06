"""Bot lifecycle management and HTTP control routes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
)

from .bot.context import BotContext
from .bot.handlers import (
    build_handler,
    recent_handler,
    start_handler,
    status_handler,
)
from .config import Config
from .drive.uploader import DriveUploader
from .jenkins.client import JenkinsClient

logger = logging.getLogger(__name__)


def _build_application(bot_context: BotContext) -> Application:
    """Create a Telegram application wired with the existing handlers."""
    application = ApplicationBuilder().token(bot_context.config.telegram_token).build()
    application.bot_data["bot_context"] = bot_context
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", start_handler))
    application.add_handler(CommandHandler("build", build_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(CommandHandler("recent", recent_handler))
    return application


class BotManager:
    """Manage Telegram bot startup, shutdown, and status."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._application: Application | None = None
        self._bot_context: BotContext | None = None
        self._config: Config | None = None
        self._last_error: str | None = None

    @property
    def bot_context(self) -> BotContext | None:
        return self._bot_context

    @property
    def running(self) -> bool:
        return self._application is not None and self._bot_context is not None

    async def start(self, config: Config) -> None:
        """Build and start the Telegram polling application."""
        async with self._lock:
            if self.running:
                return

            missing = []
            if not config.telegram_token:
                missing.append("TELEGRAM_BOT_TOKEN")
            if not config.jenkins_url:
                missing.append("JENKINS_URL")
            if not config.jenkins_user:
                missing.append("JENKINS_USER")
            if not config.jenkins_api_token:
                missing.append("JENKINS_API_TOKEN")
            if missing:
                raise ValueError(
                    f"Missing required configuration: {', '.join(missing)}"
                )

            try:
                jenkins = JenkinsClient(
                    url=config.jenkins_url,
                    user=config.jenkins_user,
                    api_token=config.jenkins_api_token,
                    job_name=config.jenkins_job_name,
                )
                drive = DriveUploader(token_path=config.oauth_token_path)

                # Two-step construction: application.bot is only available
                # after _build_application() runs, so we build a bootstrap
                # context with bot=None first, then replace it with the real
                # context once the application object exists.
                bootstrap_context = BotContext(
                    config=config,
                    jenkins=jenkins,
                    drive=drive,
                    bot=None,  # type: ignore[arg-type]
                )
                application = _build_application(bootstrap_context)
                bot_context = BotContext(
                    config=config,
                    jenkins=jenkins,
                    drive=drive,
                    bot=application.bot,
                )
                application.bot_data["bot_context"] = bot_context

                await application.initialize()
                await application.start()
                if not application.updater:
                    raise RuntimeError("Application.updater is None after start")
                await application.updater.start_polling(drop_pending_updates=True)

                self._application = application
                self._bot_context = bot_context
                self._config = config
                self._last_error = None
                logger.info("Telegram bot started")
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("Failed to start Telegram bot")
                raise

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

            # Close the reusable httpx client
            if self._bot_context:
                await self._bot_context.jenkins.close()

            self._application = None
            self._bot_context = None
            self._config = None

    async def restart(self, config: Config) -> None:
        """Restart the Telegram polling application."""
        await self.stop()
        await self.start(config)

    def status(self) -> dict[str, Any]:
        """Return the current bot manager status."""
        bot_context = self._bot_context
        return {
            "configured": self._config is not None,
            "running": self.running,
            "drive_connected": (
                bot_context.drive.is_connected() if bot_context else False
            ),
            "pending_builds": (bot_context.pending_count if bot_context else 0),
            "last_error": self._last_error,
            "job_id": self._config.jenkins_job_id if self._config else None,
        }


control_router = APIRouter(prefix="/control", tags=["control"])


def _get_manager(request: Request) -> BotManager:
    return request.app.state.manager


@control_router.post("/start")
async def start_bot(request: Request) -> dict[str, Any]:
    """Start the Telegram bot if it is not already running."""
    manager = _get_manager(request)
    config = Config.resolve()
    try:
        await manager.start(config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


@control_router.post("/stop")
async def stop_bot(request: Request) -> dict[str, Any]:
    """Stop the Telegram bot if it is running."""
    manager = _get_manager(request)
    await manager.stop()
    return manager.status()


@control_router.post("/restart")
async def restart_bot(request: Request) -> dict[str, Any]:
    """Restart the Telegram bot using the current resolved config."""
    manager = _get_manager(request)
    config = Config.resolve()
    try:
        await manager.restart(config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manager.status()


@control_router.get("/status")
async def bot_status(request: Request) -> dict[str, Any]:
    """Report whether the Telegram bot is configured and running."""
    return _get_manager(request).status()
