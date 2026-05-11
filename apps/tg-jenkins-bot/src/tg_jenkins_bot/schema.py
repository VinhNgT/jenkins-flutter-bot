"""Declarative schema for the Telegram bot configuration module.

This is the single source of truth for all bot config fields.  It drives:
  - Config.resolve()  via resolve_fields() + post_resolve()
  - GET /control/schema  via serialize_schema()
  - stack-manager rendering  via the serialized JSON
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


from config_schema import FieldDef, resolve_fields, serialize_schema  # noqa: F401

# ---------------------------------------------------------------------------
# Bot-specific constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
OAUTH_TOKEN_PATH = DATA_DIR / "oauth.json"


# ---------------------------------------------------------------------------
# Bot field declarations
# ---------------------------------------------------------------------------

MODULE_TITLE = "Telegram Bot Configuration"
MODULE_DESCRIPTION = (
    "Configures the Telegram bot that receives <code>/build</code> commands"
    " and delivers APK download links. Requires a Telegram bot token and a"
    " Jenkins server with a pipeline job ready to accept build triggers."
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
    # ── Git Repository ──
    FieldDef(
        key="git.repo_url",
        env_var="GIT_REPO_URL",
        attr="git_repo_url",
        label="Repository URL",
        group="Git Repository",
        description="Git clone URL for the Flutter project",
        help_html=(
            "The HTTPS clone URL of your repository, e.g."
            " <code>https://gitlab.com/my-group/my-flutter-app.git</code>"
            "<br><br>"
            "Used for two purposes:"
            "<ul>"
            "<li>Generating the Jenkins pipeline script</li>"
            "<li>Checking the latest commit to detect duplicate builds"
            " (GitLab only)</li>"
            "</ul>"
        ),
    ),
    FieldDef(
        key="git.access_token",
        env_var="GIT_ACCESS_TOKEN",
        attr="git_access_token",
        label="Access Token",
        group="Git Repository",
        description="GitLab token with read_api scope (enables duplicate build detection)",
        help_html=(
            "Create a <strong>Project Access Token</strong> in"
            " GitLab → Settings → Access Tokens."
            " Select the <code>read_api</code> scope.<br><br>"
            "Optional — only needed if you want the bot to skip"
            " redundant builds when the branch HEAD hasn't changed."
        ),
        secret=True,
        field_type="password",
    ),
    # ── Jenkins Connection ──
    FieldDef(
        key="jenkins.user",
        env_var="JENKINS_USER",
        attr="jenkins_user",
        label="Jenkins User",
        group="Jenkins Connection",
        description="Jenkins account with permission to trigger builds",
        required=True,
    ),
    FieldDef(
        key="jenkins.api_token",
        env_var="JENKINS_API_TOKEN",
        attr="jenkins_api_token",
        label="Jenkins API Token",
        group="Jenkins Connection",
        description="Token for triggering pipeline builds",
        help_html=(
            "In Jenkins: click your username (top-right) →"
            " <strong>Configure</strong> → <strong>API Token</strong>"
            " → <strong>Add new Token</strong> → copy the generated token."
        ),
        secret=True,
        required=True,
        field_type="password",
    ),
    FieldDef(
        key="jenkins.job_name",
        env_var="JENKINS_JOB_NAME",
        attr="jenkins_job_name",
        label="Pipeline Job Name",
        group="Jenkins Connection",
        description="Must match the pipeline job name in Jenkins",
        default="flutter-build",
    ),

    FieldDef(
        key="jenkins.credentials_id",
        env_var="JENKINS_CREDENTIALS_ID",
        attr="jenkins_credentials_id",
        label="Repo Credentials ID",
        group="Jenkins Connection",
        description="Jenkins credential ID for cloning private repos (leave empty for public repos)",
        help_html=(
            "If your Flutter project is in a <strong>private repository</strong>,"
            " Jenkins needs stored credentials to clone it.<br><br>"
            "<strong>To find or create a credential ID:</strong><br>"
            "1. Go to <strong>Manage Jenkins → Credentials</strong><br>"
            "2. Select the appropriate scope (e.g. <strong>(global)</strong>)<br>"
            "3. If you already have a credential, note its <strong>ID</strong>"
            " column value<br>"
            "4. To create one: click <strong>Add Credentials</strong> →"
            " Kind: <strong>Username with password</strong> →"
            " paste your Git PAT as the password →"
            " set an ID like <code>gitlab-credentials</code><br><br>"
            "Leave empty for public repositories — no credentials needed."
        ),
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
            " Defaults to the Drive folder name if not set,"
            ' then "your app".'
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
        key="drive.folder_name",
        env_var="DRIVE_FOLDER_NAME",
        attr="drive_folder_name",
        label="Drive Folder Name",
        group="Build Settings",
        description="Drive folder for APKs (auto-created if missing)",
    ),
    FieldDef(
        key="bot.max_recent_builds",
        env_var="MAX_RECENT_BUILDS",
        attr="max_recent_builds",
        label="Max Recent Builds",
        group="Build Settings",
        description="Build history limit (0 = unlimited)",
        default="0",
        field_type="number",
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
        key="jenkins.url",
        env_var="JENKINS_URL",
        attr="jenkins_url",
        label="Jenkins URL",
        group="Jenkins Connection",
        description="Internal Docker network URL (e.g. http://jenkins:8080)",
        required=True,
    ),
    FieldDef(
        key="bot.service_url",
        env_var="BOT_SERVICE_URL",
        attr="bot_service_url",
        label="Bot Service URL",
        group="Build Settings",
        description="Internal URL for this service (Jenkins POSTs results here, port is derived automatically)",
        default="http://tg-bot:9090",
    ),
)

# ---------------------------------------------------------------------------
# Bot-specific post-resolution
# ---------------------------------------------------------------------------


def post_resolve(
    values: dict[str, Any], config_path: Path | None = None
) -> dict[str, Any]:
    """Apply bot-specific resolution logic after generic field resolution."""
    # app_name fallback: app_name → drive_folder_name → repo name → "your app"
    if not values.get("app_name"):
        repo_name = ""
        repo_url = values.get("git_repo_url", "")
        if repo_url:
            repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
        values["app_name"] = (
            values.get("drive_folder_name") or repo_name or "your app"
        )

    # oauth_token_path — keep tokens next to the config file when possible
    resolved_path = config_path
    if resolved_path is None and os.environ.get("CONFIG_PATH"):
        resolved_path = Path(os.environ["CONFIG_PATH"])

    if resolved_path is not None:
        values["oauth_token_path"] = resolved_path.parent / "oauth.json"
    else:
        values["oauth_token_path"] = OAUTH_TOKEN_PATH

    return values
