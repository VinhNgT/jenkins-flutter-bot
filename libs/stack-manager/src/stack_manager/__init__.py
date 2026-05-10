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
    build_export_tarball as build_export_tarball,
    generate_compose_vars as generate_compose_vars,
    generate_env_files as generate_env_files,
    import_tarball as import_tarball,
)
from stack_manager.jenkins_pipeline import generate_jenkinsfile as generate_jenkinsfile
from stack_manager.project_schema import PROJECT_FIELDS as PROJECT_FIELDS
from stack_manager.project_schema import PROJECT_INFRA as PROJECT_INFRA
from stack_manager.project_schema import PROJECT_MODULE_DESCRIPTION as PROJECT_MODULE_DESCRIPTION
from stack_manager.project_schema import PROJECT_MODULE_TITLE as PROJECT_MODULE_TITLE
from stack_manager.services import ServiceClient as ServiceClient
