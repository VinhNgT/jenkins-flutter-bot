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
        "flutter-build",
        title="Jenkins Job Name",
        description="Name of the Jenkins pipeline job to trigger",
        json_schema_extra={
            "group": "Jenkins",
            "json_key": "jenkins.job_name",
        },
    )
    # ── Advanced (deployment topology) ──
    jenkins_url: str = Field(
        "http://jenkins:8080",
        title="Jenkins URL",
        description="Jenkins controller URL for API calls",
        json_schema_extra={
            "group": "Jenkins",
            "json_key": "jenkins.url",
        },
    )
    file_manager_url: str = Field(
        "http://file-manager:9092",
        title="File Manager URL",
        description="Internal URL of the file-manager service",
        json_schema_extra={
            "group": "Advanced",
            "json_key": "builds.file_manager_url",
        },
    )
    self_url: str = Field(
        "http://build-manager:9010",
        title="Self URL",
        description="Internal URL of this service (used for webhook callbacks)",
        json_schema_extra={
            "group": "Advanced",
            "json_key": "builds.self_url",
        },
    )
    build_data_path: Path = Field(
        Path("/app/data"),
        title="Build Data Path",
        description="Directory for persistent build state files",
        json_schema_extra={
            "group": "Advanced",
            "json_key": "builds.data_path",
        },
    )
