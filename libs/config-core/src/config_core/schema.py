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
import typing
from pathlib import Path
from typing import Any, Type, get_type_hints
from typing import Self

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefinedType
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from config_core.redact import register_secret


def resolve_config_path(path: Path) -> Path:
    """Apply ``JFB_DATA_DIR`` override to a config file path.

    When the ``JFB_DATA_DIR`` environment variable is set, the parent
    directory of *path* is replaced with its value while the filename is
    preserved.  This allows tests to redirect **all** config I/O to a
    temporary directory with a single env-var, requiring zero code
    changes in any consumer.

    Example::

        # Original: Path("/app/data/bot.json")
        # With JFB_DATA_DIR=/tmp/test123:
        # Result:   Path("/tmp/test123/bot.json")
    """
    override = os.environ.get("JFB_DATA_DIR")
    if override:
        return Path(override) / path.name
    return path


class JsonConfigSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source that loads JSON config.

    Resolves the config file path from (in order):
      1. ``config_path`` class variable on the settings model
      2. ``CONFIG_PATH`` environment variable (legacy fallback)

    Reads the nested JSON structure and flattens it into a dict keyed by
    Pydantic field names, using each field's ``json_schema_extra["json_key"]``
    to locate the value via its dotted path (e.g. ``"agent.name"`` →
    ``{"agent": {"name": ...}}``).  Fields without a ``json_key`` are looked
    up by field name at the top level of the JSON.
    """

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        # Implementation is deferred to __call__ to load the whole dict
        return None, "", False

    @staticmethod
    def _resolve_dotted(data: dict[str, Any], dotted_key: str) -> Any:
        """Walk a nested dict following a dotted key path.

        Returns a sentinel ``_MISSING`` when the path does not exist so we
        can distinguish "key absent" from "key present with value None".
        """
        current: Any = data
        for part in dotted_key.split("."):
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = current[part]
        return current

    def __call__(self) -> dict[str, Any]:
        load_dotenv()

        # Determine the config file path from the settings class.
        cls_path = getattr(self.settings_cls, "config_path", None)
        if cls_path is None:
            return {}

        path = resolve_config_path(Path(cls_path))
        if not path.exists():
            return {}

        try:
            raw: dict[str, Any] = json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}

        # 2. Flatten the nested JSON into {field_name: value} using
        #    each field's json_key to locate the value.
        #    Empty strings are skipped so they don't override Pydantic
        #    defaults or env-var fallbacks for required/typed fields.
        result: dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            extra = field.json_schema_extra or {}
            if not isinstance(extra, dict):
                extra = {}
            json_key = str(extra.get("json_key", field_name))
            value = self._resolve_dotted(raw, json_key)
            if value is not _MISSING and value != "":
                result[field_name] = value

        return result


# Sentinel for missing JSON keys (distinct from None).
_MISSING = object()


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
        instance = cls()

        # Close the secret lifecycle: secrets are masked on read
        # (read_masked_config) and now also scrubbed on output (logs).
        # Any field marked with json_schema_extra={"secret": True} has its
        # resolved value registered with the process-global SecretRedactor.
        for name, field in cls.model_fields.items():
            extra = field.json_schema_extra or {}
            if isinstance(extra, dict) and extra.get("secret"):
                value = getattr(instance, name, None)
                if isinstance(value, str) and value:
                    register_secret(value)

        return instance


def get_frontend_schema(cls: Type[BaseModel], title: str, description: str) -> dict[str, Any]:
    """Convert Pydantic model fields to the config-hub frontend schema format.

    Defaults are resolved from two transparent sources:
      1. Hardcoded Pydantic field default
      2. Environment variable (field name uppercased, matching pydantic-settings)

    A field is only marked ``required`` in the UI when *neither* source
    provides a value.  For secret fields the env presence suppresses the
    required marker but the actual value is never revealed.
    """
    fields = []
    
    for name, field in cls.model_fields.items():
        raw_extra = field.json_schema_extra or {}
        extra: dict[str, Any] = raw_extra if isinstance(raw_extra, dict) else {}
        is_secret = extra.get("secret", False)

        # All ServiceSettings fields are visible in the dashboard

        # 1. Check for a hardcoded Pydantic default.
        #    Fields with default_factory have field.default set to
        #    PydanticUndefined — skip those.
        has_pydantic_default = (
            not field.is_required()
            and field.default is not None
            and not isinstance(field.default, PydanticUndefinedType)
        )

        display_default = ""
        if has_pydantic_default:
            if isinstance(field.default, list):
                display_default = ", ".join(str(x) for x in field.default)
            else:
                display_default = str(field.default)

        # 2. Check environment for a fallback default.
        #    This makes deployment-injected values (e.g. JENKINS_URL from
        #    docker-compose) transparent in the UI — they appear as defaults
        #    just like hardcoded Pydantic defaults.
        env_provided = False
        if not has_pydantic_default:
            env_val = os.environ.get(name.upper())
            if env_val:
                env_provided = True
                # Show the env value as the display default, but never
                # reveal secret values.
                if not is_secret:
                    display_default = env_val

        # A field is only "required" in the UI when neither a hardcoded
        # default nor an environment variable provides a value.
        effectively_required = (
            field.is_required() and not has_pydantic_default and not env_provided
        )

        # Resolve the UI input type from raw field metadata.
        # Choices is a list of [value, label] pairs from Pydantic extras.
        raw_choices: list[list[str]] = extra.get("choices", [])
        raw_type: str = extra.get("field_type", "password" if is_secret else "text")

        is_bool_choices = (
            len(raw_choices) == 2
            and any(c[0] == "true" for c in raw_choices)
            and any(c[0] == "false" for c in raw_choices)
        )

        if is_bool_choices or raw_type == "boolean":
            ui_type = "boolean"
        elif raw_choices or raw_type == "select":
            ui_type = "select"
        elif raw_type in ("integer", "number"):
            ui_type = "integer"
        else:
            ui_type = raw_type  # text, password, etc.

        # Flatten choice pairs to a simple list of option values.
        options: list[str] | None = (
            [c[0] for c in raw_choices] if raw_choices else None
        )

        field_def: dict[str, Any] = {
            "key": extra.get("json_key", name),  # Dotted key if nested, or just name
            "label": field.title or name.replace("_", " ").title(),
            "group": extra.get("group", "General"),
            "description": field.description or "",
            "help_html": extra.get("help_html", ""),
            "default": display_default,
            "secret": is_secret,
            "required": effectively_required,
            "type": ui_type,
            "options": options,
            "order": extra.get("order", 999),
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
        self.data = data if data is not None else {}

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

    The *path* is subject to the ``JFB_DATA_DIR`` override so tests can
    redirect config I/O transparently.
    """
    resolved = resolve_config_path(path)
    data: dict[str, Any] = {}
    if resolved.exists():
        data = json.loads(resolved.read_text())

    doc = ConfigDocument(data)
    secret_keys = get_secret_keys(config_cls)

    secret_lengths: dict[str, int | bool] = {}
    for key in secret_keys:
        value = doc.get(key)
        if value not in (None, ""):
            secret_lengths[key] = 8
            doc.set(key, None)
        else:
            secret_lengths[key] = False

    return {"values": doc.data, "secret_lengths": secret_lengths}


def _resolve_origin_type(annotation: Any) -> type | None:
    """Unwrap Optional/Union and return the first non-None concrete type.

    Returns ``None`` if the annotation is not a simple concrete type or a
    straightforward Optional wrapper.
    """
    origin = typing.get_origin(annotation)
    if origin is typing.Union:  # includes Optional[X] == Union[X, None]
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
        return None  # complex Union — leave as-is
    if origin is not None:
        return None  # generic like List[str], Dict[...] — leave as-is
    if isinstance(annotation, type):
        return annotation
    return None


def _coerce_payload_types(
    config_cls: type[BaseModel],
    payload: dict[str, Any],
) -> None:
    """Coerce string values in *payload* to native Python types in-place.

    The browser always submits form fields as strings.  This converts them
    to the correct type (int, float, bool, Path) using the model's field
    annotations so the JSON file stores native values that Pydantic can
    validate without error.
    """
    try:
        hints = get_type_hints(config_cls)
    except Exception:  # pragma: no cover — guard against edge cases
        return

    payload_doc = ConfigDocument(payload)

    for field_name, field in config_cls.model_fields.items():
        annotation = hints.get(field_name)
        if annotation is None:
            continue
        target_type = _resolve_origin_type(annotation)
        if target_type is None or target_type is str:
            continue  # nothing to coerce

        extra = field.json_schema_extra or {}
        if not isinstance(extra, dict):
            extra = {}
        json_key = str(extra.get("json_key", field_name))

        value = payload_doc.get(json_key)
        if not isinstance(value, str):
            continue  # already the right type (or absent)
        if value == "":
            continue  # leave empty strings for downstream handling

        try:
            if target_type is bool:
                # Interpret common truthy/falsy strings
                coerced: Any = value.lower() in ("true", "1", "yes", "on")
            elif target_type is int:
                coerced = int(value)
            elif target_type is float:
                coerced = float(value)
            elif target_type is Path:
                coerced = value  # keep as string; Path is fine as str in JSON
            else:
                coerced = target_type(value)
            payload_doc.set(json_key, coerced)
        except (ValueError, TypeError):
            pass  # leave as-is; Pydantic will surface a clear error later


def save_config_with_merge(
    config_cls: type[BaseModel],
    path: Path,
    payload: dict[str, Any],
) -> None:
    """Strip empty secrets from *payload*, deep-merge with existing, and write.

    Empty or ``None`` secret values are removed from the payload before
    merging so that ``deep_merge()`` preserves existing secret values.

    String values are coerced to their native Python type (int, float, bool)
    before writing so the JSON file stays type-correct and Pydantic can
    validate it without errors on the next load.

    The *path* is subject to the ``JFB_DATA_DIR`` override so tests can
    redirect config I/O transparently.
    """
    resolved = resolve_config_path(path)

    # Coerce form strings to native types before any other processing
    _coerce_payload_types(config_cls, payload)

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
    if resolved.exists():
        existing = json.loads(resolved.read_text())

    doc = ConfigDocument(existing)
    doc.merge(payload_doc.data)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(doc.data, indent=2))


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

