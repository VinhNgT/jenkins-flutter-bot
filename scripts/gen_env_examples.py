#!/usr/bin/env python3
"""Generate env/*.env.example files from schema declarations.

Usage:
    uv run python scripts/gen_env_examples.py

Requires ``uv sync`` so all workspace packages are importable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_core import PydanticUndefined
from pydantic_settings import BaseSettings

from agent_control.config import AgentSettings
from build_manager.config import BuildSettings
from file_manager.config import StorageSettings
from service_hub.config import ServiceHubBootstrap
from tg_bot.config import BotSettings


def _generate_example(cls: type[BaseSettings], title: str) -> list[str]:
    """Generate documentation lines for a Pydantic model."""
    lines: list[str] = [
        "",
        f"# ── {title} ──"
    ]

    # Group fields by UI group
    groups: dict[str, list[tuple[str, Any]]] = {}
    for name, field in cls.model_fields.items():
        extra = field.json_schema_extra or {}
        if not isinstance(extra, dict):
            extra = {}
        group = str(extra.get("group", "General"))
        groups.setdefault(group, []).append((name, field))

    for group_name, group_fields in groups.items():
        if group_name != "General":
            lines.append("")
            lines.append(f"# {group_name}")

        for name, field in group_fields:
            lines.append("")
            req_tag = " (required)" if field.is_required() else ""
            label = field.title or name.replace("_", " ").title()
            lines.append(f"# {label}{req_tag}")
            
            if field.description:
                lines.append(f"# {field.description}")

            env_var = name.upper()
            
            # Required fields are uncommented to signal they need filling.
            # Optional fields are commented out; show default if one exists.
            if field.is_required():
                lines.append(f"{env_var}=")
            else:
                default_val = field.default if field.default is not PydanticUndefined else ""
                lines.append(f"# {env_var}={default_val}")

    return lines


def main() -> None:
    env_path = Path(__file__).resolve().parent.parent / "infra" / "compose.env.example"
    
    lines: list[str] = [
        "# ══════════════════════════════════════════════════",
        "# Jenkins Flutter Bot — Configuration",
        "# ══════════════════════════════════════════════════",
        "# Edit this file, then run:  ./compose.sh prod up -d",
        "# To regenerate template:    uv run python scripts/gen_env_examples.py",
        "",
        "# ── Global Infrastructure ──",
        "",
        "# Cloudflare Tunnel Token",
        "# Used by cloudflared to expose the gateway to the internet",
        "# CLOUDFLARE_TUNNEL_TOKEN=",
        "",
        "# Image Tag",
        "# Tag used when pulling images from GHCR (prod/edge modes)",
        "# IMAGE_TAG=latest",
    ]

    examples: list[tuple[type[BaseSettings], str]] = [
        (ServiceHubBootstrap, "Service Hub (Infra)"),
        (BotSettings, "Telegram Bot"),
        (AgentSettings, "Agent Control"),
        (StorageSettings, "File Manager"),
        (BuildSettings, "Build Manager"),
    ]

    for cls, title in examples:
        lines.extend(_generate_example(cls, title))

    lines.append("")
    env_path.write_text("\n".join(lines))
    print(f"✓ Generated {env_path.relative_to(Path.cwd())}")

if __name__ == "__main__":
    main()
