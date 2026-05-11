"""Bot lifecycle management and HTTP control routes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from telegram import MenuButtonCommands
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .bot.callbacks import callback_router
from .bot.context import BotContext
from .bot.handlers import (
    keyboard_build_handler,
    keyboard_recent_handler,
    start_handler,
    status_handler,
    text_branch_handler,
)
from .config import Config
from .drive.uploader import DriveUploader
from .git.remote import GitRemoteClient
from .jenkins.client import JenkinsClient

logger = logging.getLogger(__name__)


def _build_application(bot_context: BotContext) -> Application:
    """Create a Telegram application wired with the new handler architecture."""
    application = ApplicationBuilder().token(bot_context.config.telegram_token).build()
    application.bot_data["bot_context"] = bot_context

    # Slash commands (kept)
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", start_handler))
    application.add_handler(CommandHandler("status", status_handler))

    # Keyboard buttons (new)
    application.add_handler(
        MessageHandler(filters.Regex("^🔨 Build$"), keyboard_build_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex("^📦 Recent$"), keyboard_recent_handler)
    )

    # Free-text branch name (new)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_branch_handler)
    )

    # Inline button callbacks (new)
    application.add_handler(CallbackQueryHandler(callback_router))

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
                git_remote: GitRemoteClient | None = None
                if config.commit_check_enabled:
                    parsed = urlparse(config.git_repo_url)
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    project_id = parsed.path.strip("/").removesuffix(".git")
                    git_remote = GitRemoteClient(
                        base_url=base_url,
                        project_id=project_id,
                        token=config.git_access_token,
                    )
                    logger.info("Commit check enabled for project: %s", project_id)

                # Two-step construction: application.bot is only available
                # after _build_application() runs, so we build a bootstrap
                # context with bot=None first, then replace it with the real
                # context once the application object exists.
                bootstrap_context = BotContext(
                    config=config,
                    github_url=config.github_url,
                    jenkins=jenkins,
                    drive=drive,
                    bot=None,  # type: ignore[arg-type]
                    git_remote=git_remote,
                )
                application = _build_application(bootstrap_context)
                bot_context = BotContext(
                    config=config,
                    github_url=config.github_url,
                    jenkins=jenkins,
                    drive=drive,
                    bot=application.bot,
                    git_remote=git_remote,
                )
                application.bot_data["bot_context"] = bot_context

                await application.initialize()
                await application.start()
                if not application.updater:
                    raise RuntimeError("Application.updater is None after start")
                await application.updater.start_polling(drop_pending_updates=True)

                # Register visible commands (replaces BotFather /setcommands)
                await application.bot.set_my_commands(
                    [
                        ("status", "Check build system health"),
                        ("help", "How to use this bot"),
                    ]
                )

                # Replace "/" icon with "📋 Menu" label
                await application.bot.set_chat_menu_button(
                    menu_button=MenuButtonCommands(),
                )

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

            # Close reusable HTTP clients
            if self._bot_context:
                await self._bot_context.jenkins.close()
                if self._bot_context.git_remote:
                    await self._bot_context.git_remote.close()

            self._application = None
            self._bot_context = None
            self._config = None

    async def restart(self, config: Config) -> None:
        """Restart the Telegram polling application."""
        await self.stop()
        await self.start(config)

    def _is_configured(self) -> bool:
        """Check whether the required user-supplied config fields are present.

        Only checks runtime fields (BOT_FIELDS) that users must configure via
        the web UI.  Infrastructure fields like ``jenkins_url`` are excluded —
        they come from environment variables and always have a working default.
        """
        try:
            config = Config.resolve()
            return bool(
                config.telegram_token
                and config.jenkins_user
                and config.jenkins_api_token
            )
        except Exception:
            logger.exception("Failed to resolve bot config during status check")
            return False

    def status(self) -> dict[str, Any]:
        """Return the current bot manager status."""
        bot_context = self._bot_context
        active_config = self._config if self.running else None
        return {
            "configured": self._is_configured(),
            "running": self.running,
            "drive_connected": (
                bot_context.drive.is_connected() if bot_context else False
            ),
            "pending_builds": (bot_context.pending_count if bot_context else 0),
            "tracked_builds": (bot_context.tracked_count if bot_context else 0),
            "last_error": self._last_error,
            "job_name": active_config.jenkins_job_name if active_config else None,
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


@control_router.get("/schema")
async def get_schema() -> dict[str, Any]:
    """Return the bot module's config field schema."""
    from .schema import (
        BOT_FIELDS,
        BOT_INFRA,
        MODULE_DESCRIPTION,
        MODULE_TITLE,
        serialize_schema,
    )

    schema = serialize_schema(BOT_FIELDS, MODULE_TITLE, MODULE_DESCRIPTION)
    schema["infra"] = serialize_schema(
        BOT_INFRA, MODULE_TITLE, MODULE_DESCRIPTION
    )["fields"]
    return schema
