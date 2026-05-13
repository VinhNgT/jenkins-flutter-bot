"""Shared configuration schema primitives.

This module is the single source of truth for the declarative config
framework used by all services in the stack.  It provides:

  - ``RuntimeFieldDef``   — frozen dataclass for UI-editable runtime config fields
  - ``InfraFieldDef``     — frozen dataclass for environment-only infrastructure fields
  - ``ConfigRegistry``    — centralized registry for managing and resolving a module's config
  - ``nested_get()``      — read a value from a nested dict by dotted key
  - ``nested_set()``      — write a value into a nested dict by dotted key
  - ``deep_merge()``      — recursively merge dicts, preserving absent keys
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeFieldDef:
    """Declarative definition for a portable, UI-editable configuration field."""

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


@dataclass(frozen=True)
class InfraFieldDef:
    """Declarative definition for an environment-only infrastructure field."""

    env_var: str  # Env var: "JENKINS_URL"
    attr: str  # Python attribute on Config: "jenkins_url"
    label: str = ""
    group: str = "Infrastructure"
    description: str = ""
    default: str = ""  # Hardcoded default
    required: bool = False
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
    """Write a value into a nested dict using a dotted key path."""
    parts = dotted_key.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def deep_merge(target: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dicts, replacing lists and primitives.

    Keys missing from `updates` are left untouched in `target`.
    """
    merged = target.copy()
    for k, v in updates.items():
        if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
            merged[k] = deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _coerce(value: str | None, value_type: str) -> Any:
    """Coerce a string value into its declared type."""
    if value is None:
        return "" if value_type == "str" else None

    try:
        match value_type:
            case "int":
                return int(value)
            case "bool":
                return str(value).lower() in ("true", "1", "yes")
            case "list[int]":
                return [int(x.strip()) for x in value.split(",") if x.strip()]
            case "str" | _:
                return str(value)
    except (ValueError, TypeError):
        return None


_BACKEND_ONLY_KEYS = {"attr", "env_var"}


class ConfigRegistry:
    """Central registry for managing a module's configuration schema and resolution."""

    def __init__(self, title: str, description: str):
        self.title = title
        self.description = description
        self.runtime_fields: list[RuntimeFieldDef] = []
        self.infra_fields: list[InfraFieldDef] = []

    def register_runtime(self, **kwargs) -> None:
        """Register a portable, UI-editable runtime configuration field."""
        self.runtime_fields.append(RuntimeFieldDef(**kwargs))

    def register_infra(self, **kwargs) -> None:
        """Register an environment-only infrastructure field."""
        self.infra_fields.append(InfraFieldDef(**kwargs))

    @property
    def secret_keys(self) -> tuple[str, ...]:
        """Return the dotted keys for all runtime fields marked as secret."""
        return tuple(f.key for f in self.runtime_fields if f.secret)

    def resolve(self, config_path: Path | None = None) -> dict[str, Any]:
        """Resolve all fields into a unified config dict.

        Resolution Priority:
          Runtime: JSON File > Environment > .env > Default
          Infra: Environment > .env > Default
        """
        load_dotenv()

        path = config_path
        if path is None and os.environ.get("CONFIG_PATH"):
            path = Path(os.environ["CONFIG_PATH"])

        file_data: dict[str, Any] = {}
        if path and path.exists():
            file_data = json.loads(path.read_text())

        values: dict[str, Any] = {}
        missing: list[str] = []

        # Resolve Runtime fields (JSON > Env > Default)
        for f in self.runtime_fields:
            raw = nested_get(file_data, f.key)
            if raw in (None, ""):
                raw = os.environ.get(f.env_var) if f.env_var else None
            if raw in (None, ""):
                raw = f.default

            coerced = _coerce(raw, f.value_type)
            values[f.attr] = coerced

            if f.required and coerced in (None, "", []):
                missing.append(f.label)

        # Resolve Infra fields (Env > Default)
        for f_infra in self.infra_fields:
            raw = os.environ.get(f_infra.env_var)
            if raw in (None, ""):
                raw = f_infra.default

            coerced = _coerce(raw, f.value_type)
            values[f.attr] = coerced

            if f.required and coerced in (None, "", []):
                missing.append(f.env_var)

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        return values

    def serialize(self) -> dict[str, Any]:
        """Serialize the runtime schema to a JSON-ready dict for the HTTP endpoint."""
        return {
            "title": self.title,
            "description": self.description,
            "fields": [
                {k: v for k, v in asdict(f).items() if k not in _BACKEND_ONLY_KEYS}
                for f in self.runtime_fields
            ],
        }
