"""Configuration core framework based on Pydantic.

Provides the shared ``ServiceSettings``, UI adapter,
dict helpers, and config I/O utilities used by every service in the stack.
"""

from config_core.schema import (
    ServiceSettings as ServiceSettings,
    ConfigDocument as ConfigDocument,
    get_frontend_schema as get_frontend_schema,
    get_secret_keys as get_secret_keys,
    read_masked_config as read_masked_config,
    save_config_with_merge as save_config_with_merge,
)
