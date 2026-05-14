"""Typed frozen config dataclass for the build manager."""

from __future__ import annotations

from pathlib import Path
from pydantic import Field
from config_core import ServiceSettings

_DEFAULT_CONFIG_PATH = Path("/app/data/builds.json")


class BuildConfig(ServiceSettings):
    """Resolved build manager configuration.

    Use ``BuildConfig.resolve()`` to build an instance from the
    standard config precedence chain (JSON → env → defaults).
    """

    # ── Jenkins ──
    jenkins_user: str = Field(
        "",
        title="Jenkins User",
        description="Username for Jenkins API authentication",
        json_schema_extra={
            "group": "Jenkins",
            "json_key": "jenkins.user",
        },
    )
    jenkins_api_token: str = Field(
        "",
        title="Jenkins API Token",
        description="API token for Jenkins authentication",
        json_schema_extra={
            "group": "Jenkins",
            "help_html": (
                "Go to Jenkins → your profile → <strong>Configure</strong>"
                " → <strong>API Token</strong> → <strong>Add new Token</strong>."
            ),
            "secret": True,
            "field_type": "password",
            "json_key": "jenkins.api_token",
        },
    )
    jenkins_job_name: str = Field(
        "flutter-build",
        title="Jenkins Job Name",
        description="Name of the Jenkins pipeline job to trigger",
        json_schema_extra={
            "group": "Jenkins",
            "json_key": "jenkins.job_name",
        },
    )
    jenkins_credentials_id: str = Field(
        "",
        title="Jenkins Credentials ID",
        description="Jenkins credential ID for private repository checkout",
        json_schema_extra={
            "group": "Jenkins",
            "help_html": (
                "Only needed for private repositories. This is the ID of a"
                " Jenkins credential that grants access to the Git repository."
                " Leave blank for public repositories."
            ),
            "json_key": "jenkins.credentials_id",
        },
    )

    # ── Git ──
    git_repo_url: str = Field(
        "",
        title="Git Repository URL",
        description="Clone URL of the Flutter project repository",
        json_schema_extra={
            "group": "Git",
            "help_html": (
                "The URL that Jenkins will use to clone the repository."
                " For public repos use HTTPS, for private repos use the"
                " URL matching your Jenkins credential type."
            ),
            "json_key": "git.repo_url",
        },
    )

    # Infra
    jenkins_url: str = Field("", json_schema_extra={"infra": True})
    file_manager_url: str = Field("http://file-manager:9092", json_schema_extra={"infra": True})
    self_url: str = Field("http://build-manager:9010", json_schema_extra={"infra": True})
    build_data_path: Path = Field(Path("/app/data"), json_schema_extra={"infra": True})

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> BuildConfig:
        """Resolve config from all sources."""
        return cls.load()
