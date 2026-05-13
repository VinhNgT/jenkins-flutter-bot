"""Self-documenting .env export/import with tarball packaging."""

from __future__ import annotations

import io
import logging
import re
import tarfile
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

    # --- Infrastructure fields (always commented out, always empty) ---
    if infra_groups:
        lines.append("")
        lines.append(f"# {'─' * 40}")
        lines.append("# Infrastructure (environment-specific, not portable)")
        lines.append("# These settings are tied to your deployment topology.")
        lines.append("# Prefer docker-compose `environment:` section; .env is also acceptable.")
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


def generate_env_files(
    bot_config: dict[str, Any],
    agent_config: dict[str, Any],
    bot_schema: dict[str, Any] | None,
    agent_schema: dict[str, Any] | None,
    drive_config: dict[str, Any] | None = None,
    drive_schema: dict[str, Any] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Generate per-service env file contents.

    Returns ``({"bot.env": "...", "agent.env": "...", "drive.env": "..."}, warnings)``.
    """
    files: dict[str, str] = {}
    all_warnings: list[str] = []

    # Bot env file
    bot_lines, bot_warnings = _build_env_lines(
        bot_schema, bot_config, "Telegram Bot"
    )
    files["bot.env"] = "\n".join(bot_lines)
    all_warnings.extend(bot_warnings)

    # Agent env file
    agent_lines, agent_warnings = _build_env_lines(
        agent_schema, agent_config, "Jenkins Agent"
    )
    files["agent.env"] = "\n".join(agent_lines)
    all_warnings.extend(agent_warnings)

    # Drive env file (OAuth credentials)
    if drive_schema and drive_config is not None:
        drive_lines, drive_warnings = _build_env_lines(
            drive_schema, drive_config, "Google Drive"
        )
        files["drive.env"] = "\n".join(drive_lines)
        all_warnings.extend(drive_warnings)

    return files, all_warnings


# ---------------------------------------------------------------------------
# Compose-compatible env var output
# ---------------------------------------------------------------------------


def generate_compose_vars(
    config_data: dict[str, Any],
    schema: dict[str, Any] | None,
    section_label: str,
) -> str:
    """Generate compose-compatible environment block for one service.

    Returns lines suitable for pasting into a ``docker-compose.yml``
    ``environment:`` block::

        TELEGRAM_BOT_TOKEN: "your-token"
        ALLOWED_CHAT_IDS: "123,456"
    """
    if not schema or "fields" not in schema:
        return f"# {section_label} schema not available\n"

    lines: list[str] = [f"# {section_label}"]
    for field_def in schema["fields"]:
        env_var = field_def.get("env_var", "")
        if not env_var:
            continue

        key = field_def["key"]
        value_type = field_def.get("value_type", "str")
        raw = nested_get(config_data, key)

        if raw not in (None, "", []):
            value = _serialize_value(raw, value_type)
            lines.append(f'{env_var}: "{value}"')
        elif field_def.get("required"):
            lines.append(f"{env_var}: \"\"  # required")
        else:
            default = field_def.get("default", "")
            if default:
                lines.append(f"# {env_var}: \"{default}\"")
            else:
                lines.append(f"# {env_var}: \"\"")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Tarball export
# ---------------------------------------------------------------------------


def build_export_tarball(
    env_files: dict[str, str],
    oauth_token_path: Path | None = None,
) -> bytes:
    """Build a ``.tar.gz`` containing env files and oauth.json (if present).

    Tarball structure::

        env/bot.env
        env/agent.env
        env/oauth.json  (if oauth_token_path exists)
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for filename, content in env_files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=f"env/{filename}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        if oauth_token_path and oauth_token_path.exists():
            tar.add(str(oauth_token_path), arcname="env/oauth.json")

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
    drive_lookup: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str], list[str], list[str], list[str]]:
    """Parse env file content and route values to bot/agent/drive patches.

    Returns (bot_patch, agent_patch, drive_patch, applied, skipped_empty,
             unrecognized, parse_errors).
    """
    applied: list[str] = []
    skipped_empty: list[str] = []
    unrecognized: list[str] = []
    parse_errors: list[str] = []
    bot_patch: dict[str, Any] = {}
    agent_patch: dict[str, Any] = {}
    drive_patch: dict[str, Any] = {}

    _drive_lookup = drive_lookup or {}

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

        # Look up in bot schema, then agent schema, then drive schema
        if env_var in bot_lookup:
            field_def = bot_lookup[env_var]
            target_patch = bot_patch
            scope = "bot"
        elif env_var in agent_lookup:
            field_def = agent_lookup[env_var]
            target_patch = agent_patch
            scope = "agent"
        elif env_var in _drive_lookup:
            field_def = _drive_lookup[env_var]
            target_patch = drive_patch
            scope = "drive"
        else:
            unrecognized.append(f"{env_var} (not in any schema, ignored)")
            continue

        # Skip empty values
        if not value:
            skipped_empty.append(f"{env_var} (empty, skipped)")
            continue

        # Set the value via dotted key
        dotted_key = field_def["key"]
        nested_set(target_patch, dotted_key, value)
        applied.append(f"{env_var} → {scope}:{dotted_key} = {value}")

    return bot_patch, agent_patch, drive_patch, applied, skipped_empty, unrecognized, parse_errors


def import_tarball(
    tarball_bytes: bytes,
    bot_schema: dict[str, Any] | None,
    agent_schema: dict[str, Any] | None,
    bot_config_path: Path | None,
    agent_config_path: Path | None,
    oauth_dest_path: Path | None = None,
    drive_schema: dict[str, Any] | None = None,
    drive_config_path: Path | None = None,
) -> ImportResult:
    """Extract a config tarball and import env files + oauth.json.

    Extracts in-memory → finds ``*.env`` files → parses each line →
    routes to correct schema → writes to JSON configs.
    If ``oauth.json`` found, copies to *oauth_dest_path*.
    """
    bot_lookup = _build_env_lookup(bot_schema)
    agent_lookup = _build_env_lookup(agent_schema)
    drive_lookup = _build_env_lookup(drive_schema)

    all_applied: list[str] = []
    all_skipped: list[str] = []
    all_unrecognized: list[str] = []
    all_parse_errors: list[str] = []
    all_warnings: list[str] = []
    oauth_imported = False

    bot_patch: dict[str, Any] = {}
    agent_patch: dict[str, Any] = {}
    drive_patch: dict[str, Any] = {}

    try:
        with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue

                name = member.name
                # Strip leading directory components for matching
                basename = Path(name).name

                # Process .env files
                if basename.endswith(".env"):
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    content = f.read().decode("utf-8", errors="replace")

                    bp, ap, dp, applied, skipped, unrec, errors = _parse_env_content(
                        content, bot_lookup, agent_lookup, drive_lookup
                    )
                    bot_patch = deep_merge(bot_patch, bp)
                    agent_patch = deep_merge(agent_patch, ap)
                    drive_patch = deep_merge(drive_patch, dp)
                    all_applied.extend(applied)
                    all_skipped.extend(skipped)
                    all_unrecognized.extend(unrec)
                    all_parse_errors.extend(errors)

                # Process oauth.json
                elif basename == "oauth.json" and oauth_dest_path:
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    oauth_dest_path.parent.mkdir(parents=True, exist_ok=True)
                    oauth_dest_path.write_bytes(f.read())
                    oauth_imported = True
                    all_applied.append(f"oauth.json → {oauth_dest_path}")

    except tarfile.TarError:
        logger.exception("Failed to extract config tarball")
        return ImportResult(
            parse_errors=["Failed to extract tarball — is it a valid .tar.gz?"]
        )

    # Write patches to config files using deep merge
    if bot_patch and bot_config_path:
        existing = load_json(bot_config_path)
        merged = deep_merge(existing, bot_patch)
        write_json(bot_config_path, merged)

    if agent_patch and agent_config_path:
        existing = load_json(agent_config_path)
        merged = deep_merge(existing, agent_patch)
        write_json(agent_config_path, merged)

    if drive_patch and drive_config_path:
        existing = load_json(drive_config_path)
        merged = deep_merge(existing, drive_patch)
        write_json(drive_config_path, merged)

    # Warn about required fields still missing after import
    for lookup, config_path, scope in [
        (bot_lookup, bot_config_path, "bot"),
        (agent_lookup, agent_config_path, "agent"),
        (drive_lookup, drive_config_path, "drive"),
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
                all_warnings.append(f"Required field '{label}' ({env_var}) still missing")

    return ImportResult(
        applied=all_applied,
        skipped_empty=all_skipped,
        unrecognized=all_unrecognized,
        parse_errors=all_parse_errors,
        warnings=all_warnings,
        oauth_imported=oauth_imported,
        configs={
            "bot": bot_patch,
            "agent": agent_patch,
            "file_manager": drive_patch,
        },
    )
