"""Mock Jenkins configuration — loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class MockJenkinsConfig(BaseSettings):
    """Configuration for the mock Jenkins server.

    All values are read from environment variables.  This service is
    dev-only so ``BaseSettings`` is used directly rather than the
    project's ``ServiceSettings`` (which requires persistent JSON).
    """

    mock_build_delay: int = 10
    mock_failure_rate: float = 0.0
    mock_port: int = 8080
