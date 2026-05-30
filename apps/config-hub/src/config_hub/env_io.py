"""Self-documenting .env export/import with tarball packaging."""

from __future__ import annotations

import io
import logging
import re
import tarfile
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from config_core import ConfigDocument


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
# Per-service env file generation
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

    Infrastructure fields (from ``schema["infra"]``) are appended in a
    separate section, always commented out and always empty — they serve
    as documentation of all possible env vars the container accepts.

    Returns (lines, warnings).
    """
    if not schema or "fields" not in schema:
        return [], [f"{section_label} schema not available — is the service running?"]

    lines: list[str] = []
    warnings: list[str] = []

    # Collect portable fields grouped by UI group
    portable_groups: dict[str, list[dict[str, Any]]] = {}
    for field_def in schema["fields"]:
        env_var = field_def.get("env_var", "")
        if not env_var:
            continue
        group = field_def.get("group", "General")
        portable_groups.setdefault(group, []).append(field_def)

    # Collect infra fields grouped by UI group
    infra_groups: dict[str, list[dict[str, Any]]] = {}
    for field_def in schema.get("infra", []):
        env_var = field_def.get("env_var", "")
        if not env_var:
            continue
        group = field_def.get("group", "General")
        infra_groups.setdefault(group, []).append(field_def)

    if not portable_groups and not infra_groups:
        return [], []

    # --- Portable fields (with values) ---
    lines.append(f"# {'─' * 40}")
    lines.append(f"# {section_label}")
    lines.append(f"# {'─' * 40}")

    for group_name, fields in portable_groups.items():
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

            doc = ConfigDocument(config_data)
            raw = doc.get(key)

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

    # --- Infrastructure fields (always commented out, always empty) ---
    if infra_groups:
        lines.append("")
        lines.append(f"# {'─' * 40}")
        lines.append("# Infrastructure (environment-specific, not portable)")
        lines.append("# These settings are tied to your deployment topology.")
        lines.append(
            "# Prefer docker-compose `environment:` section; .env is also acceptable."
        )
        lines.append(f"# {'─' * 40}")

        for group_name, fields in infra_groups.items():
            lines.append("")
            lines.append(f"# ── {group_name} ──")

            for field_def in fields:
                env_var = field_def["env_var"]
                key = field_def["key"]
                label = field_def.get("label", key)
                description = field_def.get("description", "")
                default = field_def.get("default", "")
                lines.append("")

                req_tag = " (required)" if field_def.get("required", False) else ""
                lines.append(f"# {label}{req_tag}")
                if description:
                    lines.append(f"# {description}")
                if default:
                    lines.append(f"# Default: {default}")
                lines.append(f"# {env_var}=")

    lines.append("")
    return lines, warnings


def generate_compose_env(
    bot_config: dict[str, Any],
    agent_config: dict[str, Any],
    bot_schema: dict[str, Any] | None,
    agent_schema: dict[str, Any] | None,
    file_manager_config: dict[str, Any] | None = None,
    file_manager_schema: dict[str, Any] | None = None,
    builds_config: dict[str, Any] | None = None,
    builds_schema: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    """Generate a single compose.env file containing all service configurations."""
    lines: list[str] = [
        "# ══════════════════════════════════════════════════",
        "# Jenkins Flutter Bot — Exported Configuration",
        "# ══════════════════════════════════════════════════",
        "# This file contains the portable environment variables.",
        "",
    ]
    all_warnings: list[str] = []

    configs = [
        (bot_schema, bot_config, "Telegram Bot"),
        (agent_schema, agent_config, "Jenkins Agent"),
        (file_manager_schema, file_manager_config, "File Manager"),
        (builds_schema, builds_config, "Build Manager"),
    ]

    for schema, config, label in configs:
        if schema and config is not None:
            section_lines, warnings = _build_env_lines(schema, config, label)
            if section_lines:
                lines.extend(section_lines)
            all_warnings.extend(warnings)

    return "\n".join(lines), all_warnings


# ---------------------------------------------------------------------------
# Compose-compatible env var output
# ---------------------------------------------------------------------------


# Removed generate_compose_vars as it's no longer needed


# ---------------------------------------------------------------------------
# Tarball export
# ---------------------------------------------------------------------------


def build_export_tarball(
    compose_env: str,
    json_configs: dict[str, dict[str, Any]],
    oauth_token: dict[str, Any] | None = None,
    vpn_file: bytes | None = None,
) -> bytes:
    """Build a ``.tar.gz`` containing the full infrastructure state.

    Tarball structure::

        compose.env
        data/bot.json
        data/agent.json
        data/storage.json
        data/builds.json
        data/oauth.json     (if available)
        data/client.ovpn    (if available)
    """
    buf = io.BytesIO()

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Add compose.env
        env_data = compose_env.encode("utf-8")
        info = tarfile.TarInfo(name="compose.env")
        info.size = len(env_data)
        tar.addfile(info, io.BytesIO(env_data))

        # Map scopes to JSON filenames
        filename_map = {
            "bot": "bot.json",
            "agent": "agent.json",
            "file_manager": "storage.json",
            "builds": "builds.json",
        }

        # Add data/*.json files
        for scope, config_data in json_configs.items():
            if not config_data:
                continue
            fname = filename_map.get(scope, f"{scope}.json")
            json_str = json.dumps(config_data, indent=2).encode("utf-8")
            info = tarfile.TarInfo(name=f"data/{fname}")
            info.size = len(json_str)
            tar.addfile(info, io.BytesIO(json_str))

        # Add data/oauth.json
        if oauth_token:
            oauth_str = json.dumps(oauth_token, indent=2).encode("utf-8")
            info = tarfile.TarInfo(name="data/oauth.json")
            info.size = len(oauth_str)
            tar.addfile(info, io.BytesIO(oauth_str))

        # Add data/client.ovpn
        if vpn_file:
            info = tarfile.TarInfo(name="data/client.ovpn")
            info.size = len(vpn_file)
            tar.addfile(info, io.BytesIO(vpn_file))

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Import (tarball)
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
    """Structured feedback from a config import operation."""

    applied: list[str] = field(default_factory=list)
    skipped_empty: list[str] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    oauth_imported: bool = False
    configs: dict[str, dict[str, Any]] = field(default_factory=dict)


def _build_env_lookup(
    schema: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Build a lookup from env_var → field metadata.

    Includes only portable fields (``schema["fields"]``) so that imports
    only write portable config to the JSON files. Infra fields must be
    configured via environment variables or docker-compose, never JSON.
    """
    if not schema or "fields" not in schema:
        return {}

    return {f["env_var"]: f for f in schema["fields"] if f.get("env_var")}


def _parse_env_content(
    content: str,
    bot_lookup: dict[str, dict[str, Any]],
    agent_lookup: dict[str, dict[str, Any]],
    file_manager_lookup: dict[str, dict[str, Any]] | None = None,
    builds_lookup: dict[str, dict[str, Any]] | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[str],
    list[str],
    list[str],
    list[str],
]:
    """Parse env file content and route values to bot/agent/file_manager/builds patches."""
    applied: list[str] = []
    skipped_empty: list[str] = []
    unrecognized: list[str] = []
    parse_errors: list[str] = []
    bot_patch: dict[str, Any] = {}
    agent_patch: dict[str, Any] = {}
    file_manager_patch: dict[str, Any] = {}
    builds_patch: dict[str, Any] = {}

    _file_manager_lookup = file_manager_lookup or {}
    _builds_lookup = builds_lookup or {}

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

        # Look up in schemas
        if env_var in bot_lookup:
            field_def = bot_lookup[env_var]
            target_patch = bot_patch
            scope = "bot"
        elif env_var in agent_lookup:
            field_def = agent_lookup[env_var]
            target_patch = agent_patch
            scope = "agent"
        elif env_var in _file_manager_lookup:
            field_def = _file_manager_lookup[env_var]
            target_patch = file_manager_patch
            scope = "file_manager"
        elif env_var in _builds_lookup:
            field_def = _builds_lookup[env_var]
            target_patch = builds_patch
            scope = "builds"
        else:
            unrecognized.append(f"{env_var} (not in any schema, ignored)")
            continue

        # Skip empty values
        if not value:
            skipped_empty.append(f"{env_var} (empty, skipped)")
            continue

        # Set the value via dotted key
        dotted_key = field_def["key"]
        doc = ConfigDocument(target_patch)
        doc.set(dotted_key, value)
        applied.append(f"{env_var} → {scope}:{dotted_key} = {value}")

    return (
        bot_patch,
        agent_patch,
        file_manager_patch,
        builds_patch,
        applied,
        skipped_empty,
        unrecognized,
        parse_errors,
    )


def import_tarball(
    tarball_bytes: bytes,
    bot_schema: dict[str, Any] | None = None,
    agent_schema: dict[str, Any] | None = None,
    file_manager_schema: dict[str, Any] | None = None,
    builds_schema: dict[str, Any] | None = None,
) -> ImportResult:
    """Extract a config tarball and merge contents into service configs.

    Parses JSON config files if present. If compose.env is present,
    merges those environment variables using schema lookups.
    """
    bot_lookup = _build_env_lookup(bot_schema)
    agent_lookup = _build_env_lookup(agent_schema)
    file_manager_lookup = _build_env_lookup(file_manager_schema)
    builds_lookup = _build_env_lookup(builds_schema)

    all_applied: list[str] = []
    all_skipped: list[str] = []
    all_unrecognized: list[str] = []
    all_parse_errors: list[str] = []
    all_warnings: list[str] = []
    oauth_imported: bool = False

    configs: dict[str, dict[str, Any]] = {
        "bot": {},
        "agent": {},
        "file_manager": {},
        "builds": {},
    }

    try:
        with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue

                name = member.name
                basename = Path(name).name

                if basename == "oauth.json":
                    oauth_imported = True
                    continue

                # Process JSON configs first (if any logic depends on order, JSON is base)
                if basename in (
                    "bot.json",
                    "agent.json",
                    "storage.json",
                    "builds.json",
                ):
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    content = f.read().decode("utf-8", errors="replace")
                    try:
                        data = json.loads(content)
                    except Exception as e:
                        all_parse_errors.append(f"Failed to parse {basename}: {e}")
                        continue

                    scope_map = {
                        "bot.json": "bot",
                        "agent.json": "agent",
                        "storage.json": "file_manager",
                        "builds.json": "builds",
                    }
                    scope = scope_map[basename]

                    # Merge JSON data over current configs dict
                    doc = ConfigDocument(configs[scope])
                    doc.merge(data)
                    configs[scope] = doc.data
                    all_applied.append(f"Imported full config from {basename}")

                # Process compose.env
                elif basename == "compose.env" and name.endswith("compose.env"):
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    content = f.read().decode("utf-8", errors="replace")

                    bp, ap, fmp, bu_p, applied, skipped, unrec, errors = (
                        _parse_env_content(
                            content,
                            bot_lookup,
                            agent_lookup,
                            file_manager_lookup,
                            builds_lookup,
                        )
                    )
                    doc_bot = ConfigDocument(configs["bot"])
                    doc_bot.merge(bp)
                    configs["bot"] = doc_bot.data

                    doc_agent = ConfigDocument(configs["agent"])
                    doc_agent.merge(ap)
                    configs["agent"] = doc_agent.data

                    doc_fm = ConfigDocument(configs["file_manager"])
                    doc_fm.merge(fmp)
                    configs["file_manager"] = doc_fm.data

                    doc_bu = ConfigDocument(configs["builds"])
                    doc_bu.merge(bu_p)
                    configs["builds"] = doc_bu.data

                    all_applied.extend(applied)
                    all_skipped.extend(skipped)
                    all_unrecognized.extend(unrec)
                    all_parse_errors.extend(errors)

    except tarfile.TarError:
        logger.exception("Failed to extract config tarball")
        return ImportResult(
            parse_errors=["Failed to extract tarball — is it a valid .tar.gz?"]
        )

    return ImportResult(
        applied=all_applied,
        skipped_empty=all_skipped,
        unrecognized=all_unrecognized,
        parse_errors=all_parse_errors,
        warnings=all_warnings,
        oauth_imported=oauth_imported,
        configs=configs,
    )
