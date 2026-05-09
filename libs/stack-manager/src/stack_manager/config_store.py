"""Framework-agnostic JSON config file I/O and schema metadata helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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

    Raises ``ValueError`` when *path* is ``None`` — callers in web frameworks
    should catch this and translate to an appropriate HTTP error.
    """
    if path is None:
        raise ValueError("Config path not set")
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
