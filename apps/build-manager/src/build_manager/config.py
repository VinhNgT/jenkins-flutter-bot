"""Typed frozen config dataclass for the build manager."""

from __future__ import annotations

from pathlib import Path
from pydantic import Field
from config_core import ServiceSettings

_DEFAULT_CONFIG_PATH = Path("/app/data/builds.json")


class BuildSettings(ServiceSettings):
    """Resolved build manager configuration."""

    # ── Jenkins ──
    jenkins_user: str = Field(
        title="Jenkins User",
        description="Username for Jenkins API authentication",
        json_schema_extra={
            "group": "Jenkins",
            "help_html": "Your Jenkins username used for authenticating API calls.",
            "json_key": "jenkins.user",
        },
    )
    jenkins_api_token: str = Field(
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
        title="Jenkins Job Name",
        description="Name of the Jenkins pipeline job to trigger",
        json_schema_extra={
            "group": "Jenkins",
            "help_html": "The exact name of the Jenkins pipeline job that the bot should trigger.",
            "json_key": "jenkins.job_name",
        },
    )
    # ── Advanced (deployment topology) ──
    jenkins_url: str = Field(
        title="Jenkins URL",
        description="Jenkins controller URL for API calls",
        json_schema_extra={
            "group": "Jenkins",
            "help_html": "URL of the Jenkins controller (e.g., <code>http://jenkins:8080</code> for internal, or <code>https://jenkins.yourdomain.com</code> if external).",
            "json_key": "jenkins.url",
        },
    )
    file_manager_url: str = Field(
        title="File Manager URL",
        description="Internal URL of the file-manager service",
        json_schema_extra={
            "group": "Advanced",
            "help_html": "Internal URL of the file-manager service (e.g., <code>http://file-manager:9092</code>). Normally provided by the deployment environment.",
            "json_key": "builds.file_manager_url",
        },
    )
    self_url: str = Field(
        title="Self URL",
        description="Internal URL of this service (used for webhook callbacks)",
        json_schema_extra={
            "group": "Advanced",
            "help_html": "Internal URL of this service (e.g., <code>http://build-manager:9010</code>). Normally provided by the deployment environment.",
            "json_key": "builds.self_url",
        },
    )
    build_data_path: Path = Field(
        Path("/app/data"),
        title="Internal Storage Directory",
        description="Directory for persistent build state files",
        json_schema_extra={
            "group": "Advanced",
            "help_html": "The directory inside the container where the build manager persists its state. You normally do not need to change this.",
            "json_key": "builds.data_path",
        },
    )
