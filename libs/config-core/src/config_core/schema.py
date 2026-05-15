"""Shared configuration schema primitives based on Pydantic.

This module provides:
  - ``BootstrapSettings`` — Env-only config resolved once at process start (hard crash)
  - ``ServiceSettings``   — JSON > Env config loaded on demand by managers (soft fail)
  - ``get_frontend_schema`` — Adapter to convert Pydantic schema to config-hub UI format
  - ``ConfigDocument``      — Object-oriented wrapper for dict manipulation
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Type
from typing import Self

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class JsonConfigSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source that loads JSON config from CONFIG_PATH."""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        # Implementation is deferred to __call__ to load the whole dict
        return None, "", False

    def __call__(self) -> dict[str, Any]:
        load_dotenv()
        path_str = os.environ.get("CONFIG_PATH")
        if not path_str:
            return {}

        path = Path(path_str)
        if not path.exists():
            return {}

        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}


class BootstrapSettings(BaseSettings):
    """Config resolved once at process start. Hard crash if invalid.

    Sources: Environment Variables > .env file > Defaults
    No JSON file — not editable via the dashboard.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="ignore",
    )

    @classmethod
    def load(cls) -> Self:
        """Load bootstrap config from env vars. Raises ValidationError if invalid."""
        load_dotenv()
        return cls()


class ServiceSettings(BaseSettings):
    """Config loaded on demand by service managers. Soft fail → pending state.

    Sources: JSON Config File > Environment Variables > .env file > Defaults
    All fields are visible in the dashboard and re-read on manager restart.
    Missing required fields raise ValidationError (caught by manager).
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # JSON file overrides Environment Variables
        return (JsonConfigSettingsSource(settings_cls), env_settings, dotenv_settings, init_settings)

    @classmethod
    def load(cls) -> Self:
        """Load config from JSON + env. Raises ValidationError if invalid."""
        load_dotenv()
        return cls()


def get_frontend_schema(cls: Type[BaseModel], title: str, description: str) -> dict[str, Any]:
    """Convert Pydantic model fields to the config-hub frontend schema format."""
    fields = []
    
    for name, field in cls.model_fields.items():
        raw_extra = field.json_schema_extra or {}
        extra: dict[str, Any] = raw_extra if isinstance(raw_extra, dict) else {}

        # All ServiceSettings fields are visible in the dashboard

        field_def: dict[str, Any] = {
            "key": extra.get("json_key", name),  # Dotted key if nested, or just name
            "label": field.title or name.replace("_", " ").title(),
            "group": extra.get("group", "General"),
            "description": field.description or "",
            "help_html": extra.get("help_html", ""),
            "default": str(field.default) if field.default is not None and not field.is_required() else "",
            "secret": extra.get("secret", False),
            "required": field.is_required(),
            "field_type": extra.get("field_type", "password" if extra.get("secret", False) else "text"),
            "choices": extra.get("choices", []),
            "value_type": "str",  # Simplified, since pydantic parses everything
        }
        fields.append(field_def)

    return {
        "title": title,
        "description": description,
        "fields": fields,
    }


class ConfigDocument:
    """Wrapper for manipulating nested configuration dictionaries."""

    def __init__(self, data: dict[str, Any] | None = None):
        self.data = data or {}

    def get(self, dotted_key: str) -> Any:
        """Read a value from a nested dict using a dotted key path."""
        current: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def set(self, dotted_key: str, value: Any) -> None:
        """Write a value into a nested dict using a dotted key path."""
        parts = dotted_key.split(".")
        current = self.data
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    def merge(self, updates: dict[str, Any]) -> None:
        """Recursively merge dicts, replacing lists and primitives."""
        self.data = self._deep_merge(self.data, updates)

    @classmethod
    def _deep_merge(cls, target: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        merged = target.copy()
        for k, v in updates.items():
            if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                merged[k] = cls._deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged


# ---------------------------------------------------------------------------
# Shared config I/O helpers — used by all schema-owning services
# ---------------------------------------------------------------------------


def get_secret_keys(cls: type[BaseModel]) -> list[str]:
    """Extract dotted keys for all secret fields from a Pydantic model.

    Returns the ``json_key`` (or field name) for every field whose
    ``json_schema_extra`` marks it as ``secret: True``.
    """
    keys: list[str] = []
    for name, field in cls.model_fields.items():
        raw_extra = field.json_schema_extra or {}
        extra: dict[str, Any] = raw_extra if isinstance(raw_extra, dict) else {}
        if extra.get("secret"):
            key = extra.get("json_key", name)
            if isinstance(key, str):
                keys.append(key)
    return keys


def read_masked_config(
    config_cls: type[BaseModel],
    path: Path,
) -> dict[str, Any]:
    """Read a JSON config file and mask secret values.

    Returns ``{"values": <dict>, "secret_lengths": <dict>}`` where
    secret values are replaced with ``None`` and their original lengths
    are tracked for the dashboard UI.
    """
    data: dict[str, Any] = {}
    if path.exists():
        data = json.loads(path.read_text())

    doc = ConfigDocument(data)
    secret_keys = get_secret_keys(config_cls)

    secret_lengths: dict[str, int | bool] = {}
    for key in secret_keys:
        value = doc.get(key)
        if value not in (None, ""):
            secret_lengths[key] = len(str(value))
            doc.set(key, None)
        else:
            secret_lengths[key] = False

    return {"values": doc.data, "secret_lengths": secret_lengths}


def save_config_with_merge(
    config_cls: type[BaseModel],
    path: Path,
    payload: dict[str, Any],
) -> None:
    """Strip empty secrets from *payload*, deep-merge with existing, and write.

    Empty or ``None`` secret values are removed from the payload before
    merging so that ``deep_merge()`` preserves existing secret values.
    """
    payload_doc = ConfigDocument(payload)
    secret_keys = get_secret_keys(config_cls)

    # Strip empty/None secrets to avoid overwriting existing values
    for key in secret_keys:
        value = payload_doc.get(key)
        if value is None or value == "":
            parts = key.split(".")
            container: Any = payload_doc.data
            for part in parts[:-1]:
                if isinstance(container, dict):
                    container = container.get(part, {})
                else:
                    container = None
                    break
            if isinstance(container, dict):
                container.pop(parts[-1], None)

    # Deep merge with existing
    existing: dict[str, Any] = {}
    if path.exists():
        existing = json.loads(path.read_text())

    doc = ConfigDocument(existing)
    doc.merge(payload_doc.data)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc.data, indent=2))


def format_validation_error(exc: Exception) -> str:
    """Format a config validation error for the dashboard UI.

    Converts raw Pydantic ``ValidationError`` into human-readable
    summaries (e.g. "Missing required fields: secret, token").
    Falls back to ``str(exc)`` for non-Pydantic exceptions.
    """
    from pydantic import ValidationError

    if not isinstance(exc, ValidationError):
        return str(exc)

    errors = exc.errors()
    missing = [
        ".".join(str(loc) for loc in e["loc"])
        for e in errors
        if e["type"] == "missing"
    ]
    other = [
        f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in errors
        if e["type"] != "missing"
    ]

    parts: list[str] = []
    if missing:
        parts.append(f"Missing required fields: {', '.join(missing)}")
    if other:
        parts.extend(other)

    return "; ".join(parts) if parts else str(exc)

