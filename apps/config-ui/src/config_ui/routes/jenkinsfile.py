"""Jenkinsfile generator — produces a customized pipeline script."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config_schema import nested_get
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["jenkinsfile"])

# ---------------------------------------------------------------------------
# Groovy template fragments
#
# Use str.format() with {{/}} for literal Groovy braces and {name} for
# Python substitution.  Triple single-quotes (''') avoid conflicts with
# Groovy triple double-quotes (""").
# ---------------------------------------------------------------------------

_CHECKOUT_PRIVATE = '''\
        stage('Checkout') {{
            steps {{
                checkout([$class: 'GitSCM',
                    branches: [[name: "*/${{params.BRANCH}}"]],
                    userRemoteConfigs: [[
                        url: '{repo_url}',
                        credentialsId: '{credentials_id}'
                    ]]
                ])
            }}
        }}'''

_CHECKOUT_PUBLIC = '''\
        stage('Clone') {{
            steps {{
                git branch: "${{params.BRANCH}}",
                    url: '{repo_url}'
            }}
        }}'''

# NOTE: Groovy triple-double-quotes (""") appear literally in this template.
# Python triple-single-quotes (''') delimit the string so there's no conflict.
_PIPELINE_TEMPLATE = '''\
pipeline {{
    agent {{ label 'flutter' }}

    parameters {{
        string(name: 'BRANCH', defaultValue: 'main')
        string(name: 'BOT_CALLBACK_URL', defaultValue: '')
        string(name: 'BOT_REQUEST_ID', defaultValue: '')
        string(name: 'BOT_JOB_ID', defaultValue: '')
    }}

    stages {{
{checkout}

        stage('Build APK') {{
            steps {{
                sh 'flutter pub get'
                sh 'flutter build apk --release'
            }}
        }}
    }}

    post {{
        success {{
            script {{
                if (params.BOT_CALLBACK_URL) {{
                    def apkPath = 'build/app/outputs/flutter-apk/app-release.apk'
                    def commitHash = ''
                    try {{
                        commitHash = sh(script: 'git rev-parse --verify HEAD', returnStdout: true).trim()
                    }} catch (e) {{
                        commitHash = ''
                    }}
                    def metadata = groovy.json.JsonOutput.toJson([
                        request_id : params.BOT_REQUEST_ID,
                        job_id     : params.BOT_JOB_ID,
                        status     : 'success',
                        commit_hash: commitHash,
                    ])

                    sh """
                        curl -X POST "${{params.BOT_CALLBACK_URL}}" \\\\
                            -F 'metadata=${{metadata}}' \\\\
                            -F "artifact=@${{apkPath}}"
                    """
                }}
            }}
        }}

        failure {{
            script {{
                if (params.BOT_CALLBACK_URL) {{
                    def commitHash = ''
                    try {{
                        commitHash = sh(script: 'git rev-parse --verify HEAD', returnStdout: true).trim()
                    }} catch (e) {{
                        commitHash = ''
                    }}
                    def logs = currentBuild.rawBuild.getLog(50).join('\\n')
                    def metadata = groovy.json.JsonOutput.toJson([
                        request_id : params.BOT_REQUEST_ID,
                        job_id     : params.BOT_JOB_ID,
                        status     : 'failure',
                        commit_hash: commitHash,
                        logs       : logs,
                    ])

                    sh """
                        curl -X POST "${{params.BOT_CALLBACK_URL}}" \\\\
                            -F 'metadata=${{metadata}}'
                    """
                }}
            }}
        }}
    }}
}}
'''


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_bot_config(config_path: Path | None) -> dict[str, Any]:
    """Read the bot config JSON file, returning {} if missing."""
    if config_path and config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except Exception:
            logger.exception("Failed to read bot config at %s", config_path)
    return {}


def _generate_jenkinsfile(repo_url: str, credentials_id: str) -> str:
    """Generate a complete Jenkinsfile pipeline script."""
    if credentials_id:
        checkout = _CHECKOUT_PRIVATE.format(
            repo_url=repo_url, credentials_id=credentials_id
        )
    else:
        checkout = _CHECKOUT_PUBLIC.format(repo_url=repo_url)

    return _PIPELINE_TEMPLATE.format(checkout=checkout)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/jenkinsfile")
async def get_jenkinsfile(request: Request) -> dict[str, Any]:
    """Generate a Jenkinsfile pipeline script from current bot config."""
    settings = request.app.state.settings
    bot_data = _read_bot_config(settings.bot_config_path)

    repo_url = nested_get(bot_data, "git.repo_url") or ""
    credentials_id = nested_get(bot_data, "jenkins.credentials_id") or ""

    warnings: list[str] = []
    if not repo_url:
        repo_url = "<YOUR_REPO_URL>"
        warnings.append(
            "Repository URL not configured — update it in the Bot config tab."
        )

    script = _generate_jenkinsfile(repo_url, credentials_id)

    return {"script": script, "warnings": warnings}
