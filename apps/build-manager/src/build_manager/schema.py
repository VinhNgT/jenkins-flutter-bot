"""Declarative schema for the build manager configuration module.

Owns the Jenkins connection and Git repository field declarations.
"""

from __future__ import annotations

from config_schema import ConfigRegistry

# ---------------------------------------------------------------------------
# Build manager field declarations
# ---------------------------------------------------------------------------

registry = ConfigRegistry(
    title="Build Manager Configuration",
    description=(
        "Configures the build manager's connection to Jenkins and the"
        " Git repository used for builds."
    ),
)

# ── Jenkins ──
registry.register_runtime(
    key="jenkins.user",
    env_var="JENKINS_USER",
    attr="jenkins_user",
    label="Jenkins User",
    group="Jenkins",
    description="Username for Jenkins API authentication",
    required=True,
)
registry.register_runtime(
    key="jenkins.api_token",
    env_var="JENKINS_API_TOKEN",
    attr="jenkins_api_token",
    label="Jenkins API Token",
    group="Jenkins",
    description="API token for Jenkins authentication",
    help_html=(
        "Go to Jenkins → your profile → <strong>Configure</strong>"
        " → <strong>API Token</strong> → <strong>Add new Token</strong>."
    ),
    secret=True,
    required=True,
    field_type="password",
)
registry.register_runtime(
    key="jenkins.job_name",
    env_var="JENKINS_JOB_NAME",
    attr="jenkins_job_name",
    label="Jenkins Job Name",
    group="Jenkins",
    description="Name of the Jenkins pipeline job to trigger",
    default="flutter-build",
)
registry.register_runtime(
    key="jenkins.credentials_id",
    env_var="JENKINS_CREDENTIALS_ID",
    attr="jenkins_credentials_id",
    label="Jenkins Credentials ID",
    group="Jenkins",
    description="Jenkins credential ID for private repository checkout",
    help_html=(
        "Only needed for private repositories. This is the ID of a"
        " Jenkins credential that grants access to the Git repository."
        " Leave blank for public repositories."
    ),
)

# ── Git ──
registry.register_runtime(
    key="git.repo_url",
    env_var="GIT_REPO_URL",
    attr="git_repo_url",
    label="Git Repository URL",
    group="Git",
    description="Clone URL of the Flutter project repository",
    help_html=(
        "The URL that Jenkins will use to clone the repository."
        " For public repos use HTTPS, for private repos use the"
        " URL matching your Jenkins credential type."
    ),
    required=True,
)


# ---------------------------------------------------------------------------
# Infrastructure fields (environment-specific, not portable)
# ---------------------------------------------------------------------------

registry.register_infra(
    env_var="JENKINS_URL",
    attr="jenkins_url",
    required=True,
)
registry.register_infra(
    env_var="FILE_MANAGER_URL",
    attr="file_manager_url",
    default="http://file-manager:9092",
)
registry.register_infra(
    env_var="SELF_URL",
    attr="self_url",
    default="http://build-manager:9010",
)
