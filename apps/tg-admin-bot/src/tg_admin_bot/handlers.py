"""Telegram admin bot handlers — stack management via inline keyboard."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from config_schema import nested_get
from stack_manager import (
    DriveOAuth,
    ServiceClient,
    generate_env,
    generate_jenkinsfile,
    load_json,
    parse_and_import,
)
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
        "⚙️ *Admin Panel*\n\nChoose an action:",
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

    client: ServiceClient = context.bot_data["service_client"]
    bot_status = await client.status("bot")
    agent_status = await client.status("agent")

    def _icon(s: dict[str, Any]) -> str:
        if not s.get("available"):
            return "⚫"
        return "🟢" if s.get("running") else "🔴"

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
    # Parse "svc_{action}_{service}"
    parts = data.split("_", 2)
    if len(parts) != 3:
        return
    _, action, service = parts

    client: ServiceClient = context.bot_data["service_client"]
    method = getattr(client, action, None)
    if method is None:
        return

    result = await method(service)
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
    """Generate and send the .env file."""
    query = update.callback_query
    assert query is not None
    await query.answer("Generating .env…")

    settings: Settings = context.bot_data["settings"]
    client: ServiceClient = context.bot_data["service_client"]
    drive_oauth: DriveOAuth = context.bot_data["drive_oauth"]

    bot_schema = await client.schema("bot")
    agent_schema = await client.schema("agent")
    bot_data = load_json(settings.bot_config_path)
    agent_data = load_json(settings.agent_config_path)

    content, warnings = generate_env(
        bot_config=bot_data,
        agent_config=agent_data,
        bot_schema=bot_schema,
        agent_schema=agent_schema,
        oauth_exists=drive_oauth.token_path.exists(),
    )

    # Send as document
    import io

    doc = io.BytesIO(content.encode())
    doc.name = ".env"
    await query.message.reply_document(  # type: ignore[union-attr]
        document=doc, caption="📤 Generated `.env` configuration"
    )

    if warnings:
        warn_text = "\n".join(f"⚠️ {w}" for w in warnings)
        await query.message.reply_text(warn_text)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Import .env (file upload flow)
# ---------------------------------------------------------------------------


async def _import_env_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Ask the user to upload a .env file."""
    query = update.callback_query
    assert query is not None
    await query.answer()
    await query.edit_message_text(
        "📥 *Import Configuration*\n\n"
        "Send me a `.env` file to import.\n"
        "Use /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return IMPORT_WAITING


async def _import_env_receive(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receive and process the uploaded .env file."""
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
    content = raw.decode("utf-8", errors="replace")

    client: ServiceClient = context.bot_data["service_client"]
    bot_schema = await client.schema("bot")
    agent_schema = await client.schema("agent")

    result = parse_and_import(
        content=content,
        bot_schema=bot_schema,
        agent_schema=agent_schema,
        bot_config_path=settings.bot_config_path,
        agent_config_path=settings.agent_config_path,
    )

    lines: list[str] = ["📥 *Import Results*\n"]

    if result.applied:
        lines.append(f"✅ *Applied ({len(result.applied)}):*")
        for item in result.applied[:15]:
            lines.append(f"  • `{item}`")
        if len(result.applied) > 15:
            lines.append(f"  _… and {len(result.applied) - 15} more_")

    if result.skipped_empty:
        lines.append(f"\n⏭ *Skipped ({len(result.skipped_empty)} empty)*")

    if result.unrecognized:
        lines.append(f"\n❓ *Unrecognized ({len(result.unrecognized)}):*")
        for item in result.unrecognized[:10]:
            lines.append(f"  • `{item}`")

    if result.parse_errors:
        lines.append(f"\n❌ *Parse errors ({len(result.parse_errors)}):*")
        for item in result.parse_errors[:10]:
            lines.append(f"  • {item}")

    if result.warnings:
        lines.append("\n⚠️ *Warnings:*")
        for item in result.warnings:
            lines.append(f"  • {item}")

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
    bot_data = load_json(settings.bot_config_path)

    repo_url = nested_get(bot_data, "git.repo_url") or "<YOUR_REPO_URL>"
    credentials_id = nested_get(bot_data, "jenkins.credentials_id") or ""

    script = generate_jenkinsfile(repo_url, credentials_id)

    import io

    doc = io.BytesIO(script.encode())
    doc.name = "Jenkinsfile"
    await query.message.reply_document(  # type: ignore[union-attr]
        document=doc, caption="📋 Generated Jenkinsfile"
    )


# ---------------------------------------------------------------------------
# Drive OAuth — headless code-paste flow
# ---------------------------------------------------------------------------


async def _drive_setup_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Start Drive OAuth flow — ask for client_id."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    drive_oauth: DriveOAuth = context.bot_data["drive_oauth"]
    settings: Settings = context.bot_data["settings"]

    # Check current status
    ui_data = load_json(settings.ui_config_path)
    client_id = nested_get(ui_data, "drive.client_id") or ""
    client_secret = nested_get(ui_data, "drive.client_secret") or ""

    if drive_oauth.token_path.exists():
        status = drive_oauth.status(client_id, client_secret)
        if status.get("connected"):
            await query.edit_message_text(
                "🔑 *Google Drive*\n\n"
                f"✅ Connected — token at `{drive_oauth.token_path}`\n\n"
                "To reconnect, delete the token first via config-ui "
                "or manually remove the file.",
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
    """Receive client_secret, generate consent URL."""
    settings: Settings = context.bot_data["settings"]
    if not _ensure_authorized(settings, update):
        return ConversationHandler.END

    client_secret = update.message.text.strip()  # type: ignore[union-attr]
    client_id = context.user_data.get("drive_client_id", "")  # type: ignore[union-attr]

    drive_oauth: DriveOAuth = context.bot_data["drive_oauth"]
    try:
        auth_url = drive_oauth.start(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://localhost",
        )
    except Exception:
        logger.exception("Failed to start Drive OAuth flow")
        await update.message.reply_text(  # type: ignore[union-attr]
            "❌ Failed to start OAuth flow. Check your credentials."
        )
        return ConversationHandler.END

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
    """Receive OAuth code, exchange for tokens."""
    settings: Settings = context.bot_data["settings"]
    if not _ensure_authorized(settings, update):
        return ConversationHandler.END

    code = update.message.text.strip()  # type: ignore[union-attr]
    client_id = context.user_data.get("drive_client_id", "")  # type: ignore[union-attr]
    client_secret = context.user_data.get("drive_client_secret", "")  # type: ignore[union-attr]

    drive_oauth: DriveOAuth = context.bot_data["drive_oauth"]
    try:
        drive_oauth.exchange_code(
            code=code, client_id=client_id, client_secret=client_secret
        )
    except Exception:
        logger.exception("Drive OAuth code exchange failed")
        await update.message.reply_text(  # type: ignore[union-attr]
            "❌ Code exchange failed. The code may have expired.\n"
            "Use /admin → 🔑 Setup Drive to try again."
        )
        return ConversationHandler.END

    await update.message.reply_text(  # type: ignore[union-attr]
        "✅ *Google Drive connected!*\n\n"
        f"Token saved to `{drive_oauth.token_path}`",
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
        "⚙️ *Admin Panel*\n\nChoose an action:",
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
