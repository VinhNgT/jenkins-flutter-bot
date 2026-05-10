"""JSON config file I/O, secret handling for config-ui.

Core I/O functions (load_json, write_json, deep_merge, nested_set, etc.)
are imported from shared libraries.  This module adds the config-ui-specific
secret masking and form handling layer on top.
"""

from __future__ import annotations

import json
from typing import Any

from config_schema import nested_get, nested_set
from fastapi import HTTPException
from stack_manager import load_json
from stack_manager import write_json as _write_json
from stack_manager.config_store import (
    extract_defaults as extract_defaults,
    extract_required_fields as extract_required_fields,
    extract_secret_fields as extract_secret_fields,
)

from .schema import DRIVE_FIELDS

# Re-export shared functions so existing intra-package imports keep working.
load_json = load_json
nested_get = nested_get
nested_set = nested_set

# ---------------------------------------------------------------------------
# Drive scope constants — derived from the local schema
# ---------------------------------------------------------------------------

DRIVE_SECRET_FIELDS = tuple(f.key for f in DRIVE_FIELDS if f.secret)
DRIVE_DEFAULTS = {f.key: f.default for f in DRIVE_FIELDS if f.default}
DRIVE_REQUIRED_FIELDS = tuple(f.key for f in DRIVE_FIELDS if f.required)


# ---------------------------------------------------------------------------
# Framework bridge — catches ValueError from stack_manager.write_json
# ---------------------------------------------------------------------------


def write_json(path: Any, data: dict[str, Any]) -> None:
    """Write JSON, converting ValueError to HTTPException."""
    try:
        _write_json(path, data)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Nested dict helpers (kept locally — only used by secret handling)
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
