"""Typed frozen config dataclass for the build manager."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import Field
from config_core import ServiceSettings

_DEFAULT_CONFIG_PATH = Path("/app/data/builds.json")


class BuildSettings(ServiceSettings):
    """Resolved build manager configuration."""

    config_path: ClassVar[Path] = _DEFAULT_CONFIG_PATH

    # ── Jenkins ──
    jenkins_user: str = Field(
        title="Jenkins User",
        description="Username for Jenkins API authentication",
        json_schema_extra={
            "group": "Jenkins",
            "order": 1,
            "help_html": "Your Jenkins username used for authenticating API calls.",
            "json_key": "jenkins.user",
        },
    )
    jenkins_api_token: str = Field(
        title="Jenkins API Token",
        description="API token for Jenkins authentication",
        json_schema_extra={
            "group": "Jenkins",
            "order": 2,
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
            "order": 3,
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
            "order": 4,
            "help_html": "URL of the Jenkins controller (e.g., <code>http://jenkins:8080</code> for internal, or <code>https://jenkins.yourdomain.com</code> if external).",
            "json_key": "jenkins.url",
        },
    )
    file_manager_url: str = Field(
        title="File Manager URL",
        description="Internal URL of the file-manager service",
        json_schema_extra={
            "group": "Advanced",
            "order": 1,
            "help_html": "Internal URL of the file-manager service (e.g., <code>http://file-manager:9092</code>). Normally provided by the deployment environment.",
            "json_key": "builds.file_manager_url",
        },
    )
    build_timeout: int = Field(
        30,
        title="Build Timeout (minutes)",
        description="How long before a pending build is considered dead and its frontend is notified",
        json_schema_extra={
            "group": "Advanced",
            "order": 2,
            "json_key": "builds.build_timeout",
        },
    )
    poll_interval: int = Field(
        10,
        title="Poll Interval (seconds)",
        description="How often to check Jenkins for build completion",
        json_schema_extra={
            "group": "Advanced",
            "order": 3,
            "help_html": (
                "Seconds between Jenkins API checks while a build is "
                "running. Lower values give faster notifications but "
                "increase API traffic."
            ),
            "json_key": "builds.poll_interval",
        },
    )
    artifact_pattern: str = Field(
        "*.apk",
        title="Artifact Pattern",
        description="Glob pattern to match build artifacts in the Jenkins archive",
        json_schema_extra={
            "group": "Advanced",
            "order": 4,
            "help_html": (
                "Pattern to find the build artifact. Default "
                "<code>*.apk</code> matches any APK. Change to "
                "<code>*.aab</code> for app bundles."
            ),
            "json_key": "builds.artifact_pattern",
        },
    )
    build_data_path: Path = Field(
        Path("/app/data"),
        title="Internal Storage Directory",
        description="Directory for persistent build state files",
        json_schema_extra={
            "group": "Advanced",
            "order": 5,
            "help_html": "The directory inside the container where the build manager persists its state. You normally do not need to change this.",
            "json_key": "builds.data_path",
        },
    )

    agent_control_url: str = Field(
        "",
        title="Agent Control URL",
        description="Internal URL of the agent-control service for VPN management during builds",
        json_schema_extra={
            "group": "Advanced",
            "order": 6,
            "help_html": (
                "Internal URL of the agent-control service "
                "(e.g., <code>http://agent-control:9091</code>). "
                "Required when VPN is enabled — the build manager connects "
                "the VPN before triggering builds and disconnects after "
                "the last build completes."
            ),
            "json_key": "builds.agent_control_url",
        },
    )

