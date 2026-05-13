"""Bot lifecycle management and HTTP control routes.

The bot is a thin Telegram frontend — all build orchestration is
delegated to the build-orchestrator service via :class:`OrchClient`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

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
    build_handler,
    recent_handler,
    start_handler,
    status_handler,
    text_branch_handler,
)
from .config import Config
from .orch_client import OrchClient

logger = logging.getLogger(__name__)


def _build_application(bot_context: BotContext) -> Application:
    """Create a Telegram application wired with the handler architecture."""
    application = ApplicationBuilder().token(bot_context.config.telegram_token).build()
    application.bot_data["bot_context"] = bot_context

    # Slash commands
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", start_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(CommandHandler("build", build_handler))
    application.add_handler(CommandHandler("recent", recent_handler))

    # Free-text branch name (for the "✏️ Type a name" path)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_branch_handler)
    )

    # Inline button callbacks
    application.add_handler(CallbackQueryHandler(callback_router))

    return application


class BotManager:
    """Manage Telegram bot startup, shutdown, and status."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._application: Application | None = None
        self._bot_context: BotContext | None = None
        self._config: Config | None = None
        self._orch_client: OrchClient | None = None
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
            if not config.orchestrator_url:
                missing.append("ORCHESTRATOR_URL")
            if missing:
                raise ValueError(
                    f"Missing required configuration: {', '.join(missing)}"
                )

            try:
                orch_client = OrchClient(config.orchestrator_url)

                # Two-step construction: application.bot is only available
                # after _build_application() runs, so we build a bootstrap
                # context with bot=None first, then replace it with the real
                # context once the application object exists.
                bootstrap_context = BotContext(
                    config=config,
                    orch_client=orch_client,
                    bot=None,  # type: ignore[arg-type]
                )
                application = _build_application(bootstrap_context)
                bot_context = BotContext(
                    config=config,
                    orch_client=orch_client,
                    bot=application.bot,
                )
                application.bot_data["bot_context"] = bot_context

                await application.initialize()
                await application.start()
                if not application.updater:
                    raise RuntimeError("Application.updater is None after start")
                await application.updater.start_polling(drop_pending_updates=True)

                # Register visible commands in the "/" picker
                await application.bot.set_my_commands(
                    [
                        ("build", "Trigger a new build"),
                        ("recent", "Show recent builds"),
                        ("status", "Check build system health"),
                        ("help", "How to use this bot"),
                    ]
                )

                self._application = application
                self._bot_context = bot_context
                self._config = config
                self._orch_client = orch_client
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
            if self._orch_client:
                await self._orch_client.close()

            self._application = None
            self._bot_context = None
            self._config = None
            self._orch_client = None

    async def restart(self, config: Config) -> None:
        """Restart the Telegram polling application."""
        await self.stop()
        await self.start(config)

    def _is_configured(self) -> bool:
        """Check whether the required user-supplied config fields are present.

        Only checks runtime fields (BOT_FIELDS) that users must configure via
        the web UI.
        """
        try:
            config = Config.resolve()
            return bool(config.telegram_token)
        except Exception:
            logger.exception("Failed to resolve bot config during status check")
            return False

    def status(self) -> dict[str, Any]:
        """Return the current bot manager status."""
        return {
            "configured": self._is_configured(),
            "running": self.running,
            "pending_builds": (
                self._bot_context.pending_count if self._bot_context else 0
            ),
            "last_error": self._last_error,
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
    schema["infra"] = serialize_schema(BOT_INFRA, MODULE_TITLE, MODULE_DESCRIPTION)[
        "fields"
    ]
    return schema


@control_router.get("/config")
async def get_config() -> dict[str, Any]:
    """Return current config values with secrets masked."""
    import json
    import os
    from pathlib import Path

    from config_schema import nested_get, nested_set

    from .schema import BOT_FIELDS, BOT_INFRA

    secret_keys = tuple(f.key for f in BOT_FIELDS + BOT_INFRA if f.secret)

    config_path_str = os.environ.get("CONFIG_PATH")
    config_path = Path(config_path_str) if config_path_str else None

    data: dict[str, Any] = {}
    if config_path and config_path.exists():
        data = json.loads(config_path.read_text())

    secret_lengths: dict[str, int | bool] = {}
    for key in secret_keys:
        value = nested_get(data, key)
        if value not in (None, ""):
            secret_lengths[key] = len(str(value))
            nested_set(data, key, None)
        else:
            secret_lengths[key] = False

    return {"values": data, "secret_lengths": secret_lengths}


@control_router.put("/config")
async def put_config(request: Request) -> dict[str, Any]:
    """Save config values with deep merge to preserve existing fields."""
    import json
    import os
    from pathlib import Path

    from config_schema import deep_merge, nested_get

    from .schema import BOT_FIELDS, BOT_INFRA

    config_path_str = os.environ.get("CONFIG_PATH")
    if not config_path_str:
        return {"status": "error", "detail": "CONFIG_PATH not set"}
    config_path = Path(config_path_str)

    payload = await request.json()

    # Strip empty/None secrets to avoid overwriting existing values
    secret_keys = tuple(f.key for f in BOT_FIELDS + BOT_INFRA if f.secret)
    for key in secret_keys:
        value = nested_get(payload, key)
        if value is None or value == "":
            parts = key.split(".")
            container: Any = payload
            for part in parts[:-1]:
                if isinstance(container, dict):
                    container = container.get(part, {})
                else:
                    container = None
                    break
            if isinstance(container, dict):
                container.pop(parts[-1], None)

    # Deep merge with existing
    existing: dict[str, Any] = {}
    if config_path.exists():
        existing = json.loads(config_path.read_text())

    merged = deep_merge(existing, payload)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(merged, indent=2))

    return {"status": "saved"}


# ---------------------------------------------------------------------------
# Build event callback (from build-orchestrator)
# ---------------------------------------------------------------------------

callback_event_router = APIRouter(tags=["callback"])


@callback_event_router.post("/callback/build-result")
async def handle_build_result(request: Request) -> dict[str, str]:
    """Receive a build result forwarded by the build-orchestrator.

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
    manager = _get_manager(request)
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
