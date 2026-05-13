"""Declarative configuration schema framework.

Provides the shared ``RuntimeFieldDef``, ``InfraFieldDef`` dataclasses,
config-resolution helpers, and ``ConfigRegistry`` used by every service
in the Jenkins Flutter Bot stack.
"""

from config_schema.schema import (
    RuntimeFieldDef as RuntimeFieldDef,
    InfraFieldDef as InfraFieldDef,
    ConfigRegistry as ConfigRegistry,
    deep_merge as deep_merge,
    nested_get as nested_get,
    nested_set as nested_set,
)
