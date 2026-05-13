"""Declarative schema for the Telegram bot configuration module.

This module is the single source of truth for all bot config fields. It drives:
  - Config.resolve()       via registry.resolve()
  - GET /control/schema    via registry.serialize()
  - config-hub rendering   via the serialized JSON
"""

from __future__ import annotations

from typing import Any

from config_schema import ConfigRegistry

# ---------------------------------------------------------------------------
# Module metadata
# ---------------------------------------------------------------------------

registry = ConfigRegistry(
    title="Telegram Bot Configuration",
    description=(
        "Configures the Telegram bot interface. You need a Bot Token from"
        " @BotFather. You must also specify which chat IDs are allowed to"
        " use the bot to prevent unauthorized access."
    ),
)

# ---------------------------------------------------------------------------
# Bot field declarations (Runtime)
# ---------------------------------------------------------------------------

# ── Telegram ──
registry.register_runtime(
    key="telegram.bot_token",
    env_var="TELEGRAM_BOT_TOKEN",
    attr="telegram_token",
    label="Bot Token",
    group="Telegram",
    description="Token from @BotFather",
    help_html=(
        'Message <a href="https://t.me/BotFather" target="_blank"'
        ' rel="noopener">@BotFather</a> with <code>/newbot</code> to get'
        " a token. It looks like <code>123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>."
    ),
    secret=True,
    required=True,
    field_type="password",
)
registry.register_runtime(
    key="telegram.allowed_chat_ids",
    env_var="TELEGRAM_ALLOWED_CHAT_IDS",
    attr="allowed_chat_ids",
    label="Allowed Chat IDs",
    group="Telegram",
    description="Comma-separated list of chat IDs allowed to use the bot",
    help_html=(
        "You can find your chat ID by messaging"
        ' <a href="https://t.me/userinfobot" target="_blank"'
        ' rel="noopener">@userinfobot</a>. For groups, add the bot to the'
        " group and check the logs. Looks like <code>123456789</code> or"
        " <code>-100123456789</code>."
    ),
    required=True,
    value_type="list[int]",
)
registry.register_runtime(
    key="telegram.admin_contact",
    env_var="TELEGRAM_ADMIN_CONTACT",
    attr="admin_contact",
    label="Admin Contact",
    group="Telegram",
    description="Shown to unauthorized users (e.g. '@username' or 'an admin')",
    default="an admin",
)

# ── Application ──
registry.register_runtime(
    key="bot.app_name",
    env_var="BOT_APP_NAME",
    attr="app_name",
    label="App Name",
    group="Application",
    description="Name of the app being built (used in messages)",
    default="My App",
)
registry.register_runtime(
    key="bot.branch_list",
    env_var="BOT_BRANCH_LIST",
    attr="branch_list",
    label="Git Branches",
    group="Application",
    description="Comma-separated list of branches to show in the build menu",
    default="main, develop",
)
registry.register_runtime(
    key="bot.session_ttl",
    env_var="BOT_SESSION_TTL",
    attr="session_ttl",
    label="Session TTL (seconds)",
    group="Application",
    description="How long menu sessions stay active",
    default="300",
    value_type="int",
)
registry.register_runtime(
    key="bot.build_timeout",
    env_var="BOT_BUILD_TIMEOUT",
    attr="build_timeout",
    label="Build Timeout (seconds)",
    group="Application",
    description="How long before a pending build is considered dead",
    default="1800",
    value_type="int",
)

# ── Project ──
registry.register_runtime(
    key="project.github_url",
    env_var="GITHUB_URL",
    attr="github_url",
    label="GitHub Repository URL",
    group="Project",
    description="Used to generate links to commits in Telegram messages",
    help_html=(
        "The public web URL of your GitHub repository."
        " Used only by the bot to make commit hashes clickable in Telegram."
        " Example: <code>https://github.com/my-org/my-repo</code>."
    ),
    required=True,
)

# ---------------------------------------------------------------------------
# Infrastructure fields (Environment-only)
# ---------------------------------------------------------------------------

registry.register_infra(
    env_var="BOT_SERVICE_URL",
    attr="bot_service_url",
    default="http://tg-bot:9090",
    required=True,
)
registry.register_infra(
    env_var="BUILD_MANAGER_URL",
    attr="build_manager_url",
    default="http://build-manager:9010",
    required=True,
)

# ---------------------------------------------------------------------------
# Bot-specific post-resolution
# ---------------------------------------------------------------------------

def post_resolve(values: dict[str, Any]) -> dict[str, Any]:
    """Apply bot-specific post-processing to resolved config values."""
    if "branch_list" in values and isinstance(values["branch_list"], str):
        raw_branches = values["branch_list"].split(",")
        values["branch_list"] = [b.strip() for b in raw_branches if b.strip()]

    return values
