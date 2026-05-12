"""Declarative schema for the Telegram bot configuration module.

This is the single source of truth for all bot config fields.  It drives:
  - Config.resolve()  via resolve_fields() + post_resolve()
  - GET /control/schema  via serialize_schema()
  - stack-manager rendering  via the serialized JSON
"""

from __future__ import annotations

from typing import Any


from config_schema import FieldDef, resolve_fields, serialize_schema  # noqa: F401


# ---------------------------------------------------------------------------
# Bot field declarations
# ---------------------------------------------------------------------------

MODULE_TITLE = "Telegram Bot Configuration"
MODULE_DESCRIPTION = (
    "Configures the Telegram bot that receives <code>/build</code> commands"
    " and delivers build notifications. Build orchestration is handled"
    " by the stack-manager service."
)

BOT_FIELDS: tuple[FieldDef, ...] = (
    # ── Telegram ──
    FieldDef(
        key="telegram.bot_token",
        env_var="TELEGRAM_BOT_TOKEN",
        attr="telegram_token",
        label="Bot Token",
        group="Telegram",
        description="Authentication token for the Telegram bot",
        help_html=(
            "Open Telegram → search for <strong>@BotFather</strong>"
            " → send <code>/newbot</code> → follow the prompts."
            " Copy the token it gives you."
        ),
        secret=True,
        required=True,
        field_type="password",
    ),
    FieldDef(
        key="telegram.allowed_chat_ids",
        env_var="ALLOWED_CHAT_IDS",
        attr="allowed_chat_ids",
        label="Allowed Chat IDs",
        group="Telegram",
        description="Users authorized to trigger builds",
        help_html=(
            "Send any message to your bot, then open"
            " <code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code>"
            ' in a browser. Look for <code>"chat":{"id":…}</code>.'
            " Comma-separate multiple IDs."
        ),
        required=True,
        value_type="list[int]",
    ),
    FieldDef(
        key="telegram.admin_contact",
        env_var="ADMIN_CONTACT",
        attr="admin_contact",
        label="Admin Contact",
        group="Telegram",
        description='Shown in "contact your admin" messages (e.g. "@john_doe")',
    ),
    # ── Build Settings ──
    FieldDef(
        key="bot.app_name",
        env_var="APP_NAME",
        attr="app_name",
        label="App Name",
        group="Build Settings",
        description='Display name shown in bot messages (e.g. "MyApp")',
        help_html=(
            'Name shown to users in bot messages, e.g. "MyApp".'
            ' Defaults to "your app" if not set.'
        ),
    ),
    FieldDef(
        key="bot.branch_list",
        env_var="BRANCH_LIST",
        attr="branch_list",
        label="Branch List",
        group="Build Settings",
        description="Branches shown as quick-pick buttons (comma-separated)",
        help_html=(
            "These branches appear as tap-to-build buttons in Telegram."
            " Users can always type a custom branch name."
            "<br><br>"
            "Example: <code>main, develop, staging</code>"
        ),
        default="main",
        value_type="list[str]",
    ),
    FieldDef(
        key="bot.session_ttl",
        env_var="SESSION_TTL",
        attr="session_ttl",
        label="Session Timeout",
        group="Build Settings",
        description="Seconds before the branch picker expires",
        help_html=(
            "How long users have to pick a branch before the session"
            " auto-expires. Prevents stale build prompts in group chats."
            "<br><br>"
            "Default: <code>30</code> seconds"
        ),
        default="30",
        value_type="int",
    ),
    FieldDef(
        key="bot.build_timeout",
        env_var="BUILD_TIMEOUT",
        attr="build_timeout",
        label="Build Timeout",
        group="Build Settings",
        description="Minutes before a build is considered timed out (0 = never)",
        default="30",
        field_type="number",
        value_type="int",
    ),
    FieldDef(
        key="project.github_url",
        env_var="PROJECT_GITHUB_URL",
        attr="github_url",
        label="GitHub URL",
        group="Build Settings",
        description="Link to the project's GitHub repository",
        help_html=(
            "The public URL of your GitHub repository."
            " This is displayed in the bot's /start message for quick access."
        ),
        default="https://github.com/VinhNgT/jenkins-flutter-bot",
    ),
)

# ---------------------------------------------------------------------------
# Infrastructure fields (environment-specific, not portable)
# ---------------------------------------------------------------------------

BOT_INFRA: tuple[FieldDef, ...] = (
    FieldDef(
        key="bot.service_url",
        env_var="BOT_SERVICE_URL",
        attr="bot_service_url",
        label="Bot Service URL",
        group="Infrastructure",
        description="Internal URL for this service (stack-manager POSTs build results here)",
        default="http://tg-bot:9090",
    ),
    FieldDef(
        key="bot.stack_manager_url",
        env_var="STACK_MANAGER_URL",
        attr="stack_manager_url",
        label="Stack Manager URL",
        group="Infrastructure",
        description="Internal URL of the stack-manager service",
        default="http://stack-manager:9000",
        required=True,
    ),
)

# ---------------------------------------------------------------------------
# Bot-specific post-resolution
# ---------------------------------------------------------------------------


def post_resolve(values: dict[str, Any]) -> dict[str, Any]:
    """Apply bot-specific resolution logic after generic field resolution."""
    # app_name fallback
    if not values.get("app_name"):
        values["app_name"] = "your app"

    return values
