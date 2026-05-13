"""Telegram admin bot handlers — stack management via inline keyboard.

All operational logic is delegated to the config-hub HTTP API.
This module is purely Telegram UI formatting + httpx calls.
"""

from __future__ import annotations

import io
import logging
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import TYPE_CHECKING, Any

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

if TYPE_CHECKING:
    from .settings import Settings

logger = logging.getLogger(__name__)


def _admin_version() -> str:
    """Return the installed tg-admin-bot package version, or 'unknown'."""
    try:
        return _pkg_version("tg-admin-bot")
    except PackageNotFoundError:
        return "unknown"


def _api(settings: Settings) -> str:
    """Return the config-hub base URL."""
    return settings.config_hub_url


# ---------------------------------------------------------------------------
# Conversation states for multi-step flows
# ---------------------------------------------------------------------------

DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, DRIVE_AUTH_CODE = range(3)
IMPORT_WAITING = 10


# ---------------------------------------------------------------------------
# Authorization guard
# ---------------------------------------------------------------------------


def _ensure_authorized(settings: Settings, update: Update) -> bool:
    """Return True if the chat is authorized, False otherwise."""
    if not update.effective_chat:
        return False
    return update.effective_chat.id == settings.admin_chat_id


# ---------------------------------------------------------------------------
# Main admin panel
# ---------------------------------------------------------------------------

_ADMIN_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("🔄 Services", callback_data="services"),
        ],
        [
            InlineKeyboardButton("📤 Export .env", callback_data="export_env"),
            InlineKeyboardButton("📥 Import .env", callback_data="import_env"),
        ],
        [
            InlineKeyboardButton("📋 Jenkinsfile", callback_data="jenkinsfile"),
            InlineKeyboardButton("🔑 Setup Drive", callback_data="drive_setup"),
        ],
    ]
)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin command — show the admin control panel."""
    settings: Settings = context.bot_data["settings"]
    if not _ensure_authorized(settings, update):
        return

    await update.message.reply_text(  # type: ignore[union-attr]
        f"⚙️ *Admin Panel* `v{_admin_version()}`\n\nChoose an action:",
        reply_markup=_ADMIN_KEYBOARD,
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# Status callback
# ---------------------------------------------------------------------------


async def _status_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show service status."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    settings: Settings = context.bot_data["settings"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{_api(settings)}/api/services/status")
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Failed to fetch service status")
        data = {
            "bot": {"available": False, "running": False},
            "agent": {"available": False, "running": False},
        }

    def _icon(s: dict[str, Any]) -> str:
        if not s.get("available"):
            return "⚫"
        return "🟢" if s.get("running") else "🔴"

    bot_status = data.get("bot", {})
    agent_status = data.get("agent", {})
    text = (
        f"📊 *Service Status*\n\n"
        f"{_icon(bot_status)} *Bot:* "
        f"{'running' if bot_status.get('running') else 'stopped'}\n"
        f"{_icon(agent_status)} *Agent:* "
        f"{'running' if agent_status.get('running') else 'stopped'}"
    )

    back_btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("« Back", callback_data="back")]]
    )
    await query.edit_message_text(
        text, reply_markup=back_btn, parse_mode=ParseMode.MARKDOWN
    )


# ---------------------------------------------------------------------------
# Services callback — start / stop / restart
# ---------------------------------------------------------------------------

_SERVICES_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("▶ Start Bot", callback_data="svc_start_bot")],
        [InlineKeyboardButton("■ Stop Bot", callback_data="svc_stop_bot")],
        [InlineKeyboardButton("▶ Start Agent", callback_data="svc_start_agent")],
        [InlineKeyboardButton("■ Stop Agent", callback_data="svc_stop_agent")],
        [InlineKeyboardButton("« Back", callback_data="back")],
    ]
)


async def _services_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show service control buttons."""
    query = update.callback_query
    assert query is not None
    await query.answer()
    await query.edit_message_text(
        "🔄 *Service Control*\n\nChoose an action:",
        reply_markup=_SERVICES_KEYBOARD,
        parse_mode=ParseMode.MARKDOWN,
    )


async def _service_action_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle service start/stop actions."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    data = query.data or ""
    parts = data.split("_", 2)
    if len(parts) != 3:
        return
    _, action, service = parts

    settings: Settings = context.bot_data["settings"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_api(settings)}/api/services/{service}/{action}"
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception:
        logger.exception("Failed to %s %s", action, service)
        result = {"running": "unknown", "available": False}

    status_text = "✅" if result.get("running") or result.get("available") else "⚠️"

    await query.edit_message_text(
        f"{status_text} *{service.title()}* → `{action}`\n\n"
        f"Running: {result.get('running', 'unknown')}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("« Services", callback_data="services")]]
        ),
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# Export .env
# ---------------------------------------------------------------------------


async def _export_env_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generate and send the config tarball."""
    query = update.callback_query
    assert query is not None
    await query.answer("Generating config tarball…")

    settings: Settings = context.bot_data["settings"]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_api(settings)}/api/export/tarball")
            resp.raise_for_status()
            tarball_bytes = resp.content
    except Exception:
        logger.exception("Failed to export tarball from config-hub")
        await query.edit_message_text("❌ Failed to generate config tarball.")
        return

    doc = io.BytesIO(tarball_bytes)
    doc.name = "jfb-config.tar.gz"
    await query.message.reply_document(  # type: ignore[union-attr]
        document=doc, caption="📤 Config export tarball"
    )


# ---------------------------------------------------------------------------
# Import .env (file upload flow)
# ---------------------------------------------------------------------------


async def _import_env_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Ask the user to upload a tarball."""
    query = update.callback_query
    assert query is not None
    await query.answer()
    await query.edit_message_text(
        "📥 *Import Configuration*\n\n"
        "Send me a `.tar.gz` config tarball to import.\n"
        "Use /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return IMPORT_WAITING


async def _import_env_receive(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receive and process the uploaded config tarball."""
    settings: Settings = context.bot_data["settings"]
    if not _ensure_authorized(settings, update):
        return ConversationHandler.END

    doc = update.message.document  # type: ignore[union-attr]
    if doc is None:
        await update.message.reply_text(  # type: ignore[union-attr]
            "Please send a file, not a text message.\nUse /cancel to abort."
        )
        return IMPORT_WAITING

    file = await doc.get_file()
    raw = await file.download_as_bytearray()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_api(settings)}/api/import/tarball",
                files={"file": ("config.tar.gz", bytes(raw), "application/gzip")},
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception:
        logger.exception("Failed to import tarball via config-hub")
        await update.message.reply_text(  # type: ignore[union-attr]
            "❌ Import failed. Check config-hub logs."
        )
        return ConversationHandler.END

    lines: list[str] = ["📥 *Import Results*\n"]

    applied = result.get("applied", [])
    if applied:
        lines.append(f"✅ *Applied ({len(applied)}):*")
        for item in applied[:15]:
            lines.append(f"  • `{item}`")
        if len(applied) > 15:
            lines.append(f"  _… and {len(applied) - 15} more_")

    if result.get("oauth_imported"):
        lines.append("\n🔑 *OAuth token imported*")

    skipped = result.get("skipped_empty", [])
    if skipped:
        lines.append(f"\n⏭ *Skipped ({len(skipped)} empty)*")

    unrecognized = result.get("unrecognized", [])
    if unrecognized:
        lines.append(f"\n❓ *Unrecognized ({len(unrecognized)}):*")
        for item in unrecognized[:10]:
            lines.append(f"  • `{item}`")

    parse_errors = result.get("parse_errors", [])
    if parse_errors:
        lines.append(f"\n❌ *Parse errors ({len(parse_errors)}):*")
        for item in parse_errors[:10]:
            lines.append(f"  • {item}")

    warnings = result.get("warnings", [])
    if warnings:
        lines.append("\n⚠️ *Warnings:*")
        for item in warnings:
            lines.append(f"  • {item}")

    restart_results = result.get("restart_results", {})
    if restart_results:
        lines.append("\n🔄 *Service Restarts:*")
        for svc, status in restart_results.items():
            lines.append(f"  • {svc}: {status}")

    await update.message.reply_text(  # type: ignore[union-attr]
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Jenkinsfile
# ---------------------------------------------------------------------------


async def _jenkinsfile_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generate and send the Jenkinsfile."""
    query = update.callback_query
    assert query is not None
    await query.answer("Generating Jenkinsfile…")

    settings: Settings = context.bot_data["settings"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{_api(settings)}/api/jenkinsfile")
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Failed to generate Jenkinsfile via config-hub")
        await query.edit_message_text("❌ Failed to generate Jenkinsfile.")
        return

    script = data.get("script", "")
    doc = io.BytesIO(script.encode())
    doc.name = "Jenkinsfile"
    await query.message.reply_document(  # type: ignore[union-attr]
        document=doc, caption="📋 Generated Jenkinsfile"
    )


# ---------------------------------------------------------------------------
# Drive OAuth — headless code-paste flow via config-hub API
# ---------------------------------------------------------------------------


async def _drive_setup_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Start Drive OAuth flow — check status first."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    settings: Settings = context.bot_data["settings"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{_api(settings)}/api/drive/status")
            resp.raise_for_status()
            status = resp.json()
    except Exception:
        logger.exception("Failed to check Drive status")
        status = {"connected": False, "configured": False}

    if status.get("connected"):
        await query.edit_message_text(
            "🔑 *Google Drive*\n\n"
            "✅ Connected\n\n"
            "To reconnect, disconnect first via the web dashboard.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="back")]]
            ),
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "🔑 *Google Drive Setup*\n\n"
        "Send me your Google OAuth *Client ID*.\n"
        "Use /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return DRIVE_CLIENT_ID


async def _drive_receive_client_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receive client_id, ask for client_secret."""
    settings: Settings = context.bot_data["settings"]
    if not _ensure_authorized(settings, update):
        return ConversationHandler.END

    client_id = update.message.text.strip()  # type: ignore[union-attr]
    context.user_data["drive_client_id"] = client_id  # type: ignore[index]
    await update.message.reply_text(  # type: ignore[union-attr]
        "Now send me the *Client Secret*.\nUse /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return DRIVE_CLIENT_SECRET


async def _drive_receive_client_secret(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receive client_secret, generate consent URL via config-hub."""
    settings: Settings = context.bot_data["settings"]
    if not _ensure_authorized(settings, update):
        return ConversationHandler.END

    client_secret = update.message.text.strip()  # type: ignore[union-attr]
    client_id = context.user_data.get("drive_client_id", "")  # type: ignore[union-attr]

    # Save credentials to drive config via config-hub
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.put(
                f"{_api(settings)}/api/config/drive",
                json={"drive": {"client_id": client_id, "client_secret": client_secret}},
            )
    except Exception:
        logger.exception("Failed to save Drive credentials")

    # For headless flow, the user needs to manually use the Google consent URL
    # with redirect_uri=http://localhost, then paste the code
    from urllib.parse import quote, urlencode

    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": "http://localhost",
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/drive.file",
            "access_type": "offline",
            "prompt": "consent",
        },
        quote_via=quote,
    )
    auth_url = f"https://accounts.google.com/o/oauth2/auth?{params}"

    context.user_data["drive_client_secret"] = client_secret  # type: ignore[index]

    await update.message.reply_text(  # type: ignore[union-attr]
        "🔗 Open this URL in your browser:\n\n"
        f"`{auth_url}`\n\n"
        "After authorizing, you'll be redirected to `http://localhost?code=...`\n\n"
        "Copy the `code` parameter from the URL and send it here.\n"
        "Use /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return DRIVE_AUTH_CODE


async def _drive_receive_code(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receive OAuth code, exchange for tokens via config-hub API."""
    settings: Settings = context.bot_data["settings"]
    if not _ensure_authorized(settings, update):
        return ConversationHandler.END

    code = update.message.text.strip()  # type: ignore[union-attr]
    client_id = context.user_data.get("drive_client_id", "")  # type: ignore[union-attr]
    client_secret = context.user_data.get("drive_client_secret", "")  # type: ignore[union-attr]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_api(settings)}/api/drive/connect/exchange",
                json={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            resp.raise_for_status()
    except Exception:
        logger.exception("Drive OAuth code exchange failed")
        await update.message.reply_text(  # type: ignore[union-attr]
            "❌ Code exchange failed. The code may have expired.\n"
            "Use /admin → 🔑 Setup Drive to try again."
        )
        return ConversationHandler.END

    await update.message.reply_text(  # type: ignore[union-attr]
        "✅ *Google Drive connected!*",
        parse_mode=ParseMode.MARKDOWN,
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Back button + cancel
# ---------------------------------------------------------------------------


async def _back_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Return to the admin panel."""
    query = update.callback_query
    assert query is not None
    await query.answer()
    await query.edit_message_text(
        f"⚙️ *Admin Panel* `v{_admin_version()}`\n\nChoose an action:",
        reply_markup=_ADMIN_KEYBOARD,
        parse_mode=ParseMode.MARKDOWN,
    )


async def _cancel_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Cancel any active conversation."""
    await update.message.reply_text("Cancelled.")  # type: ignore[union-attr]
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Register all handlers
# ---------------------------------------------------------------------------


def register_handlers(app: Any) -> None:
    """Register all admin bot handlers on the Application."""
    # /admin command
    app.add_handler(CommandHandler("admin", admin_command))

    # Import .env conversation
    import_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(_import_env_callback, pattern="^import_env$")
        ],
        states={
            IMPORT_WAITING: [
                MessageHandler(filters.Document.ALL, _import_env_receive),
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_command)],
    )
    app.add_handler(import_conv)

    # Drive OAuth conversation
    drive_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(_drive_setup_callback, pattern="^drive_setup$")
        ],
        states={
            DRIVE_CLIENT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _drive_receive_client_id)
            ],
            DRIVE_CLIENT_SECRET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, _drive_receive_client_secret
                )
            ],
            DRIVE_AUTH_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _drive_receive_code)
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_command)],
    )
    app.add_handler(drive_conv)

    # Simple callback queries
    app.add_handler(CallbackQueryHandler(_status_callback, pattern="^status$"))
    app.add_handler(CallbackQueryHandler(_services_callback, pattern="^services$"))
    app.add_handler(
        CallbackQueryHandler(_service_action_callback, pattern="^svc_")
    )
    app.add_handler(CallbackQueryHandler(_export_env_callback, pattern="^export_env$"))
    app.add_handler(
        CallbackQueryHandler(_jenkinsfile_callback, pattern="^jenkinsfile$")
    )
    app.add_handler(CallbackQueryHandler(_back_callback, pattern="^back$"))
