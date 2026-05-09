"""Self-documenting .env export and validated .env import."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config_schema import deep_merge, nested_get, nested_set

from .config_store import load_json, write_json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Value serialization
# ---------------------------------------------------------------------------

_SPECIAL_CHARS = set(" #\"'$`\\!&|;()")


def _needs_quoting(value: str) -> bool:
    """Check if a value needs quoting in a .env file."""
    return bool(_SPECIAL_CHARS & set(value))


def _serialize_value(raw: Any, value_type: str) -> str:
    """Serialize a config value to its .env string representation."""
    if raw is None:
        return ""

    if value_type == "bool":
        if isinstance(raw, bool):
            return "true" if raw else "false"
        return str(raw).lower()

    if value_type in ("list[int]", "list[str]"):
        if isinstance(raw, list):
            return ",".join(str(v) for v in raw)
        return str(raw)

    return str(raw)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _build_env_lines(
    schema: dict[str, Any] | None,
    config_data: dict[str, Any],
    section_label: str,
) -> tuple[list[str], list[str]]:
    """Build self-documenting .env lines from a schema and config data.

    ALL schema-defined fields are emitted:
    - Fields with values → ``KEY=value``
    - Empty required fields → ``KEY=`` (uncommented, prompts admin)
    - Empty optional fields → ``# KEY=`` (commented out)
    - Fields using their default → commented with the default value

    Returns (lines, warnings).
    """
    if not schema or "fields" not in schema:
        return [], [f"{section_label} schema not available — is the service running?"]

    lines: list[str] = []
    warnings: list[str] = []

    # Group fields by their group label for readability
    groups: dict[str, list[dict[str, Any]]] = {}
    for field_def in schema["fields"]:
        env_var = field_def.get("env_var", "")
        if not env_var:
            continue
        group = field_def.get("group", "General")
        groups.setdefault(group, []).append(field_def)

    if not groups:
        return [], []

    lines.append(f"# {'─' * 40}")
    lines.append(f"# {section_label}")
    lines.append(f"# {'─' * 40}")

    for group_name, fields in groups.items():
        lines.append("")
        lines.append(f"# ── {group_name} ──")

        for field_def in fields:
            env_var = field_def["env_var"]
            key = field_def["key"]
            default = field_def.get("default", "")
            required = field_def.get("required", False)
            value_type = field_def.get("value_type", "str")
            label = field_def.get("label", key)
            description = field_def.get("description", "")
            lines.append("")

            # Comment block: label + description
            req_tag = " (required)" if required else ""
            lines.append(f"# {label}{req_tag}")
            if description:
                lines.append(f"# {description}")

            raw = nested_get(config_data, key)

            # Field has a value — emit it
            if raw not in (None, "", []):
                value = _serialize_value(raw, value_type)
                if _needs_quoting(value):
                    value = f'"{value}"'
                lines.append(f"{env_var}={value}")
                continue

            # Empty required field — uncommented so admin sees it needs filling
            if required:
                warnings.append(f"Required field '{label}' ({env_var}) is not set")
                lines.append(f"{env_var}=")
                continue

            # Empty optional with default — show the default as a hint
            if default:
                lines.append(f"# {env_var}={default}")
            else:
                lines.append(f"# {env_var}=")

    lines.append("")
    return lines, warnings


def generate_env(
    bot_config: dict[str, Any],
    agent_config: dict[str, Any],
    bot_schema: dict[str, Any] | None,
    agent_schema: dict[str, Any] | None,
    oauth_exists: bool,
) -> tuple[str, list[str]]:
    """Generate a complete self-documenting .env file.

    Returns ``(env_content, warnings)``.
    """
    all_lines: list[str] = []
    all_warnings: list[str] = []

    # Header
    all_lines.append(
        "# ═══════════════════════════════════════════"
        "═══════════════════════════════════"
    )
    all_lines.append("# Jenkins Flutter Bot — Production Environment")
    all_lines.append(
        "# ═══════════════════════════════════════════"
        "═══════════════════════════════════"
    )
    all_lines.append("#")
    all_lines.append("# Place this file at infra/.env on your production server.")
    all_lines.append(
        "# In production (without config-ui), services read these env vars directly."
    )
    all_lines.append("#")
    all_lines.append("# Required fields are uncommented with empty values (KEY=).")
    all_lines.append("# Optional fields are commented out (# KEY=).")
    all_lines.append("#")
    all_lines.append(
        "# See: https://github.com/VinhNgT/jenkins-flutter-bot"
    )
    all_lines.append("")

    # Bot section
    bot_lines, bot_warnings = _build_env_lines(bot_schema, bot_config, "Telegram Bot")
    all_lines.extend(bot_lines)
    all_warnings.extend(bot_warnings)

    # Agent section
    agent_lines, agent_warnings = _build_env_lines(
        agent_schema, agent_config, "Jenkins Agent"
    )
    all_lines.extend(agent_lines)
    all_warnings.extend(agent_warnings)

    # OAuth token note
    all_lines.append(f"# {'─' * 40}")
    all_lines.append("# Google Drive OAuth Token")
    all_lines.append(f"# {'─' * 40}")
    if oauth_exists:
        all_lines.append(
            "# oauth.json exists — download it from the Export tab and place at"
        )
        all_lines.append("# /config/bot/oauth.json on your production server.")
    else:
        all_lines.append(
            "# oauth.json not found — complete the Drive OAuth setup first,"
        )
        all_lines.append("# then re-export.")
        all_warnings.append(
            "Google Drive OAuth token (oauth.json) not found"
            " — Drive uploads won't work in production"
        )
    all_lines.append("")

    return "\n".join(all_lines), all_warnings


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

# Matches: KEY=VALUE  or  KEY="VALUE"  or  KEY='VALUE'
_ENV_LINE_RE = re.compile(
    r"""
    ^
    \s*                          # leading whitespace
    (?:export\s+)?               # optional 'export' prefix
    ([A-Za-z_][A-Za-z0-9_]*)    # key
    =                            # separator
    (?:                          # value group
      "((?:[^"\\]|\\.)*)"        #   double-quoted value
      |'((?:[^'\\]|\\.)*)'      #   single-quoted value
      |([^\s#]*)                 #   unquoted value
    )
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class ImportResult:
    """Structured feedback from a .env import operation."""

    applied: list[str] = field(default_factory=list)
    skipped_empty: list[str] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _build_env_lookup(
    schema: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Build a lookup from env_var → field metadata."""
    if not schema or "fields" not in schema:
        return {}
    return {f["env_var"]: f for f in schema["fields"] if f.get("env_var")}


def parse_and_import(
    content: str,
    bot_schema: dict[str, Any] | None,
    agent_schema: dict[str, Any] | None,
    bot_config_path: Path | None,
    agent_config_path: Path | None,
) -> ImportResult:
    """Parse .env content, validate against schemas, and write to JSON configs.

    Returns a structured ``ImportResult`` with detailed feedback for every
    line — applied changes, skipped empties, unrecognized vars, and parse
    errors.
    """
    bot_lookup = _build_env_lookup(bot_schema)
    agent_lookup = _build_env_lookup(agent_schema)

    applied: list[str] = []
    skipped_empty: list[str] = []
    unrecognized: list[str] = []
    parse_errors: list[str] = []
    warnings: list[str] = []

    # Accumulated config patches
    bot_patch: dict[str, Any] = {}
    agent_patch: dict[str, Any] = {}

    for line_num, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()

        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        match = _ENV_LINE_RE.match(line)
        if not match:
            parse_errors.append(f"Line {line_num}: invalid syntax: {raw_line!r}")
            continue

        env_var = match.group(1)
        # Resolve the value from whichever capture group matched
        value = match.group(2) or match.group(3) or match.group(4) or ""

        # Look up in bot schema, then agent schema
        if env_var in bot_lookup:
            field_def = bot_lookup[env_var]
            target_patch = bot_patch
            scope = "bot"
        elif env_var in agent_lookup:
            field_def = agent_lookup[env_var]
            target_patch = agent_patch
            scope = "agent"
        else:
            unrecognized.append(f"{env_var} (not in any schema, ignored)")
            continue

        # Skip empty values
        if not value:
            skipped_empty.append(f"{env_var} (empty, skipped)")
            continue

        # Set the value via dotted key
        dotted_key = field_def["key"]
        label = field_def.get("label", dotted_key)
        nested_set(target_patch, dotted_key, value)
        applied.append(f"{env_var} → {scope}:{dotted_key} = {value}")

    # Write patches to config files using deep merge
    if bot_patch and bot_config_path:
        existing = load_json(bot_config_path)
        merged = deep_merge(existing, bot_patch)
        write_json(bot_config_path, merged)

    if agent_patch and agent_config_path:
        existing = load_json(agent_config_path)
        merged = deep_merge(existing, agent_patch)
        write_json(agent_config_path, merged)

    # Warn about required fields still missing after import
    for lookup, config_path, scope in [
        (bot_lookup, bot_config_path, "bot"),
        (agent_lookup, agent_config_path, "agent"),
    ]:
        if not config_path:
            continue
        current = load_json(config_path)
        for env_var, field_def in lookup.items():
            if not field_def.get("required"):
                continue
            val = nested_get(current, field_def["key"])
            if val in (None, "", []):
                label = field_def.get("label", field_def["key"])
                warnings.append(f"Required field '{label}' ({env_var}) still missing")

    return ImportResult(
        applied=applied,
        skipped_empty=skipped_empty,
        unrecognized=unrecognized,
        parse_errors=parse_errors,
        warnings=warnings,
    )
