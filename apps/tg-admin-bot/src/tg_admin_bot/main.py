"""Admin bot entry point — CLI + Application builder."""

from __future__ import annotations

import logging

from stack_manager import DriveOAuth, ServiceClient
from telegram.ext import Application

from .handlers import register_handlers
from .settings import Settings

logger = logging.getLogger(__name__)


def _drive_token_path(settings: Settings):
    """Derive the OAuth token path from the bot config path."""
    from pathlib import Path

    if settings.bot_config_path is not None:
        return settings.bot_config_path.parent / "oauth.json"
    return Path("data/oauth.json")


def build_application(settings: Settings) -> Application:  # type: ignore[type-arg]
    """Build and configure the Telegram Application."""
    app = Application.builder().token(settings.bot_token).build()

    # Wire shared state into bot_data
    app.bot_data["settings"] = settings
    app.bot_data["service_client"] = ServiceClient(
        bot_url=settings.bot_control_url,
        agent_url=settings.agent_control_url,
    )
    app.bot_data["drive_oauth"] = DriveOAuth(
        token_path=_drive_token_path(settings),
    )

    register_handlers(app)
    return app


def cli() -> None:
    """CLI entry point for the admin bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    settings = Settings.from_env()

    if not settings.bot_token:
        logger.error("ADMIN_BOT_TOKEN is not set — cannot start.")
        return
    if not settings.admin_chat_id:
        logger.error("ADMIN_CHAT_ID is not set — cannot start.")
        return

    logger.info("Starting admin bot (chat_id=%d)…", settings.admin_chat_id)
    app = build_application(settings)
    app.run_polling(drop_pending_updates=True)
