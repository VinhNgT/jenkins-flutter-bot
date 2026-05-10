"""Shared configuration schema primitives.

This module is the single source of truth for the declarative config
framework used by all services in the stack.  It provides:

  - ``FieldDef``          — frozen dataclass describing one config field
  - ``nested_get()``      — read a value from a nested dict by dotted key
  - ``nested_set()``      — write a value into a nested dict by dotted key
  - ``deep_merge()``      — recursively merge dicts, preserving absent keys
  - ``resolve_fields()``  — resolve config with priority: file > env > .env > default
  - ``serialize_schema()``— convert field definitions to a JSON-ready dict
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Field definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldDef:
    """Declarative definition for a single configuration field."""

    key: str  # Dotted JSON key: "telegram.bot_token"
    env_var: str  # Env var fallback: "TELEGRAM_BOT_TOKEN"
    attr: str  # Python attribute on Config: "telegram_token"
    label: str  # UI label: "Bot Token"
    group: str  # UI card grouping: "Telegram"
    description: str = ""  # Short text below the label
    help_html: str = ""  # Rich HTML for ? popover
    default: str = ""  # Hardcoded default
    secret: bool = False  # Mask in UI, strip from API responses
    required: bool = False
    field_type: str = "text"  # "text", "password", "number", "select"
    choices: tuple[tuple[str, str], ...] = ()  # For select: (value, label)
    value_type: str = "str"  # "str", "int", "bool", "list[int]"


# ---------------------------------------------------------------------------
# Nested dict helpers
# ---------------------------------------------------------------------------


def nested_get(data: dict[str, Any], dotted_key: str) -> Any:
    """Read a value from a nested dict using a dotted key path."""
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def nested_set(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    """Set a value in a nested dict using a dotted key path.

    Intermediate dicts are created automatically if they don't exist.
    """
    current = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def deep_merge(existing: Any, incoming: Any) -> Any:
    """Recursively merge *incoming* dict into *existing*, preserving absent keys.

    Non-dict values in *incoming* overwrite *existing*.  Dict values are
    merged recursively so that sending ``{"a": {"b": 1}}`` only touches
    the ``a.b`` path without clobbering sibling keys.
    """
    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = {**existing}
        for key, value in incoming.items():
            merged[key] = deep_merge(merged.get(key), value)
        return merged
    return incoming


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


def _coerce(raw: Any, value_type: str) -> Any:
    """Convert a raw config value to its declared Python type."""
    if value_type == "str":
        return str(raw) if raw not in (None, "") else ""

    if value_type == "int":
        return int(raw) if raw not in (None, "") else 0

    if value_type == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() not in {"0", "false", "no", ""}

    if value_type == "list[int]":
        if isinstance(raw, list):
            return [int(v) for v in raw]
        if isinstance(raw, str) and raw:
            return [int(v.strip()) for v in raw.split(",") if v.strip()]
        return []

    if value_type == "list[str]":
        if isinstance(raw, list):
            return [str(v) for v in raw]
        if isinstance(raw, str) and raw:
            return [v.strip() for v in raw.split(",") if v.strip()]
        return []

    return raw


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def resolve_fields(
    fields: tuple[FieldDef, ...],
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve config values with priority: file > env > .env > default."""
    load_dotenv()

    path = config_path
    if path is None and os.environ.get("CONFIG_PATH"):
        path = Path(os.environ["CONFIG_PATH"])

    file_data: dict[str, Any] = {}
    if path and path.exists():
        file_data = json.loads(path.read_text())

    values: dict[str, Any] = {}
    for f in fields:
        raw = nested_get(file_data, f.key)
        if raw in (None, ""):
            raw = os.environ.get(f.env_var) if f.env_var else None
        if raw in (None, ""):
            raw = f.default
        values[f.attr] = _coerce(raw, f.value_type)

    return values


# ---------------------------------------------------------------------------
# Schema serialization (for GET /control/schema)
# ---------------------------------------------------------------------------

# Fields excluded from the serialized schema — they are backend-only concerns.
_BACKEND_ONLY_KEYS = {"attr"}


def serialize_schema(
    fields: tuple[FieldDef, ...],
    title: str,
    description: str,
) -> dict[str, Any]:
    """Serialize module schema to a JSON-ready dict for the HTTP endpoint."""
    return {
        "title": title,
        "description": description,
        "fields": [
            {k: v for k, v in asdict(f).items() if k not in _BACKEND_ONLY_KEYS}
            for f in fields
        ],
    }
