"""Declarative configuration schema framework.

Provides the shared ``FieldDef`` dataclass, config-resolution helpers,
and schema serialization used by every service in the Jenkins Flutter
Bot stack.
"""

from config_schema.schema import (
    FieldDef as FieldDef,
    deep_merge as deep_merge,
    nested_get as nested_get,
    nested_set as nested_set,
    resolve_fields as resolve_fields,
    serialize_schema as serialize_schema,
)
