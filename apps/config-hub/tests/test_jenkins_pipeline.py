"""Unit tests for the Jenkinsfile pipeline generator optimizations."""

from __future__ import annotations

from config_hub.config import HubBootstrap
from config_hub.jenkins_pipeline import generate_jenkinsfile
from config_hub.manager import ConfigHubManager


def test_generate_jenkinsfile_default_optimizations():
    """Verify that by default, properties and shallow clone are active but clean workspace is disabled."""
    jenkinsfile = generate_jenkinsfile("https://github.com/user/repo.git", "")

    # Should contain properties block
    assert "buildDiscarder" in jenkinsfile
    assert "numToKeepStr: '2'" in jenkinsfile

    # Should NOT contain cleanWs post action by default
    assert "cleanWs()" not in jenkinsfile

    # Should contain shallow clone for public repo
    assert "depth: 1" in jenkinsfile
    assert "shallow: true" in jenkinsfile


def test_generate_jenkinsfile_clean_workspace():
    """Verify that explicitly enabling clean_workspace includes cleanWs() in the output."""
    jenkinsfile = generate_jenkinsfile("https://github.com/user/repo.git", "", clean_workspace=True)
    assert "cleanWs()" in jenkinsfile


def test_generate_jenkinsfile_no_optimizations():
    """Verify that turning off optimizations correctly excludes them."""
    jenkinsfile = generate_jenkinsfile(
        "https://github.com/user/repo.git",
        "",
        discard_builds=False,
        clean_workspace=False,
        shallow_clone=False,
    )

    # Should NOT contain properties block
    assert "properties" not in jenkinsfile
    assert "buildDiscarder" not in jenkinsfile

    # Should NOT contain cleanWs
    assert "cleanWs()" not in jenkinsfile

    # Should NOT contain shallow clone options
    assert "depth: 1" not in jenkinsfile
    assert "shallow: true" not in jenkinsfile


def test_generate_jenkinsfile_private_repo_shallow_clone():
    """Verify that private repo checkout contains the CloneOption extension when shallow_clone is active."""
    jenkinsfile_with = generate_jenkinsfile(
        "git@github.com:user/repo.git",
        "my-creds",
        shallow_clone=True,
    )
    assert "CloneOption" in jenkinsfile_with
    assert "depth: 1" in jenkinsfile_with
    assert "shallow: true" in jenkinsfile_with

    jenkinsfile_without = generate_jenkinsfile(
        "git@github.com:user/repo.git",
        "my-creds",
        shallow_clone=False,
    )
    assert "CloneOption" not in jenkinsfile_without


async def test_manager_get_jenkinsfile_explicit_params():
    """Verify ConfigHubManager.get_jenkinsfile works with explicit params and has no warnings."""
    config = HubBootstrap(
        bot_control_url=None,
        agent_control_url=None,
        file_manager_url=None,
        build_manager_url=None,
    )
    manager = ConfigHubManager(config=config)

    # If repo_url and credentials_id are explicitly supplied, we should not query services or warn.
    res = await manager.get_jenkinsfile(
        repo_url="https://github.com/myorg/myrepo.git",
        credentials_id="my-github-pat",
        discard_builds=True,
        clean_workspace=True,
        shallow_clone=True,
    )

    assert "https://github.com/myorg/myrepo.git" in res["script_public"]
    assert "https://github.com/myorg/myrepo.git" in res["script_private"]
    assert "my-github-pat" in res["script_private"]
    assert "cleanWs()" in res["script_public"]
    assert "cleanWs()" in res["script_private"]
    assert not res["warnings"]  # should be empty


async def test_router_get_jenkinsfile_api(client):
    """Verify /api/jenkinsfile endpoint handles custom query parameters and passes them through."""
    response = await client.get(
        "/api/webapp-admin/jenkinsfile",
        params={
            "repo_url": "https://github.com/test-user/test-project.git",
            "credentials_id": "test-creds-id",
            "discard_builds": "true",
            "clean_workspace": "false",
            "shallow_clone": "true",
        }
    )
    assert response.status_code == 200
    data = response.json()

    assert "https://github.com/test-user/test-project.git" in data["script_public"]
    assert "test-creds-id" in data["script_private"]
    assert "cleanWs()" not in data["script_public"]
    assert not data["warnings"]
