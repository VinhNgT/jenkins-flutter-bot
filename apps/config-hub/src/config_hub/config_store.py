"""JSON config file I/O, secret handling, and schema metadata helpers.

Merges the framework-agnostic I/O from the former library with the
secret-masking layer that was previously in config-ui.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config_schema import nested_get, nested_set
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# JSON file I/O
# ---------------------------------------------------------------------------


def load_json(path: Path | None) -> dict[str, Any]:
    """Load a JSON config file, returning {} if missing or *path* is None."""
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text())


def write_json(path: Path | None, data: dict[str, Any]) -> None:
    """Write a dict as pretty-printed JSON, creating parent dirs.

    Raises ``HTTPException(500)`` when *path* is ``None``.
    """
    if path is None:
        raise HTTPException(status_code=500, detail="Config path not set")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Schema metadata extractors
# ---------------------------------------------------------------------------


def extract_secret_fields(schema: dict[str, Any] | None) -> tuple[str, ...]:
    """Extract secret field keys from a serialized schema response."""
    if not schema or "fields" not in schema:
        return ()
    return tuple(f["key"] for f in schema["fields"] if f.get("secret"))


def extract_defaults(schema: dict[str, Any] | None) -> dict[str, str]:
    """Extract default values from a serialized schema response."""
    if not schema or "fields" not in schema:
        return {}
    return {f["key"]: f["default"] for f in schema["fields"] if f.get("default")}


def extract_required_fields(schema: dict[str, Any] | None) -> tuple[str, ...]:
    """Extract required field keys from a serialized schema response."""
    if not schema or "fields" not in schema:
        return ()
    return tuple(f["key"] for f in schema["fields"] if f.get("required"))


# ---------------------------------------------------------------------------
# Nested dict helpers (used by secret handling)
# ---------------------------------------------------------------------------


def _nested_remove(data: dict[str, Any], dotted_key: str) -> None:
    """Remove a key from a nested dict using a dotted key path.

    If the key doesn't exist, this is a no-op.
    """
    current = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            return
        current = next_value
    current.pop(parts[-1], None)


# ---------------------------------------------------------------------------
# Secret handling — secrets are NEVER sent to the browser
# ---------------------------------------------------------------------------


def strip_secrets(
    data: dict[str, Any], secret_fields: tuple[str, ...]
) -> dict[str, Any]:
    """Return a deep copy with secret field values set to None.

    The browser never receives actual secret values.  Use ``secrets_set()``
    to tell the frontend which secrets have been configured.
    """
    stripped = json.loads(json.dumps(data))
    for field in secret_fields:
        if nested_get(stripped, field) is not None:
            nested_set(stripped, field, None)
    return stripped


def secrets_set(
    data: dict[str, Any], secret_fields: tuple[str, ...]
) -> dict[str, int | bool]:
    """Return ``{dotted_key: int | False}`` for each secret field.

    When a secret has a value, returns its character length so the UI can
    render the correct number of mask dots.  Returns ``False`` when unset.

    Example::

        {"telegram.bot_token": 46, "jenkins.api_token": False}
    """
    result: dict[str, int | bool] = {}
    for field in secret_fields:
        value = nested_get(data, field)
        if value not in (None, ""):
            result[field] = len(str(value))
        else:
            result[field] = False
    return result


def clean_secrets_from_payload(
    incoming: dict[str, Any], secret_fields: tuple[str, ...]
) -> dict[str, Any]:
    """Remove secret fields that are None or empty from an incoming payload.

    This prevents the frontend from accidentally overwriting real secrets
    when it sends back the stripped response without the user having edited
    the secret field.  Absent keys are preserved by ``deep_merge()``.
    """
    cleaned = json.loads(json.dumps(incoming))
    for field in secret_fields:
        value = nested_get(cleaned, field)
        if value is None or value == "":
            _nested_remove(cleaned, field)
    return cleaned
