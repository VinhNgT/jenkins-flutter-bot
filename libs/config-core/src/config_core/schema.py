"""Shared configuration schema primitives based on Pydantic.

This module provides:
  - ``ServiceSettings``   — BaseSettings class enforcing JSON > Env precedence
  - ``get_frontend_schema`` — Adapter to convert Pydantic schema to config-hub UI format
  - ``ConfigDocument``      — Object-oriented wrapper for dict manipulation
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Type

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


class ServiceSettings(BaseSettings):
    """Base configuration class enforcing JSON > Environment > Default precedence."""

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
    def load(cls) -> "ServiceSettings":
        """Load configuration using the defined precedence."""
        # load_dotenv is called in the source, but doing it here ensures it's available
        load_dotenv()
        return cls()


def get_frontend_schema(cls: Type[BaseModel], title: str, description: str) -> dict[str, Any]:
    """Convert Pydantic model fields to the config-hub frontend schema format."""
    fields = []
    
    for name, field in cls.model_fields.items():
        extra = field.json_schema_extra or {}
        
        # Skip infrastructure fields
        if extra.get("infra", False):
            continue

        field_def = {
            "key": extra.get("json_key", name), # Dotted key if nested, or just name
            "label": field.title or name.replace("_", " ").title(),
            "group": extra.get("group", "General"),
            "description": field.description or "",
            "help_html": extra.get("help_html", ""),
            "default": str(field.default) if field.default is not None and not field.is_required() else "",
            "secret": extra.get("secret", False),
            "required": field.is_required(),
            "field_type": extra.get("field_type", "password" if extra.get("secret", False) else "text"),
            "choices": extra.get("choices", []),
            "value_type": "str", # Simplified, since pydantic parses everything
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
