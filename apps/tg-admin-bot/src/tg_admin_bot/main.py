"""Admin bot entry point — CLI + Application builder."""

from __future__ import annotations

import logging

from telegram.ext import Application

from .config import AdminBotConfig
from .handlers import register_handlers

logger = logging.getLogger(__name__)


def build_application(config: AdminBotConfig) -> Application:  # type: ignore[type-arg]
    """Build and configure the Telegram Application."""
    app = Application.builder().token(config.bot_token).build()

    # Wire shared state into bot_data
    app.bot_data["config"] = config

    register_handlers(app)
    return app


def cli() -> None:
    """CLI entry point for the admin bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )

    config = AdminBotConfig.load()

    if not config.bot_token:
        logger.error("ADMIN_BOT_TOKEN is not set — cannot start.")
        return
    if not config.admin_chat_id:
        logger.error("ADMIN_CHAT_ID is not set — cannot start.")
        return

    logger.info("Starting admin bot (chat_id=%d)…", config.admin_chat_id)
    app = build_application(config)
    app.run_polling(drop_pending_updates=True)
