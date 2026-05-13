"""Configuration core framework based on Pydantic.

Provides the shared ``ServiceSettings``, UI adapter,
and dict helpers used by every service in the stack.
"""

from config_core.schema import (
    ServiceSettings as ServiceSettings,
    ConfigDocument as ConfigDocument,
    get_frontend_schema as get_frontend_schema,
)
