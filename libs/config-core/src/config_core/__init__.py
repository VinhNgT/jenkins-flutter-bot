"""Configuration core framework based on Pydantic.

Provides ``BootstrapSettings`` (env-only, hard crash),
``ServiceSettings`` (JSON > env, soft fail), UI adapter,
dict helpers, and config I/O utilities used by every service in the stack.
"""

from config_core.schema import (
    BootstrapSettings as BootstrapSettings,
    ServiceSettings as ServiceSettings,
    ConfigDocument as ConfigDocument,
    get_frontend_schema as get_frontend_schema,
    get_secret_keys as get_secret_keys,
    read_masked_config as read_masked_config,
    save_config_with_merge as save_config_with_merge,
)
