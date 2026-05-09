"""Shared operational utilities for the Jenkins Flutter Bot stack.

Provides service control, config file I/O, Drive OAuth, .env export/import,
and Jenkinsfile generation — used by both config-ui and tg-admin-bot.
"""

from stack_manager.config_store import (
    extract_defaults as extract_defaults,
    extract_required_fields as extract_required_fields,
    extract_secret_fields as extract_secret_fields,
    load_json as load_json,
    write_json as write_json,
)
from stack_manager.drive import DriveOAuth as DriveOAuth
from stack_manager.env_io import (
    ImportResult as ImportResult,
    generate_env as generate_env,
    parse_and_import as parse_and_import,
)
from stack_manager.jenkins_pipeline import generate_jenkinsfile as generate_jenkinsfile
from stack_manager.services import ServiceClient as ServiceClient
