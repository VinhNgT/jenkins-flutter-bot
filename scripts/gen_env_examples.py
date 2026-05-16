#!/usr/bin/env python3
"""Generate env/*.env.example files from schema declarations.

Usage:
    uv run python scripts/gen_env_examples.py

Requires ``uv sync`` so all workspace packages are importable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Type

from pydantic_core import PydanticUndefined
from pydantic_settings import BaseSettings

from agent_control.config import AgentSettings
from build_manager.config import BuildSettings
from config_hub.config import HubBootstrap
from file_manager.config import StorageSettings
from tg_admin_bot.config import AdminBotBootstrap
from tg_jenkins_bot.config import BotSettings


def _generate_example(cls: Type[BaseSettings], title: str) -> str:
    """Generate a self-documenting .env.example from Pydantic models."""
    lines: list[str] = [
        f"# {'─' * 50}",
        f"# {title}",
        f"# {'─' * 50}",
        "#",
        "# This example is generated from the schema definitions.",
        "# To use:  cp <name>.env.example <name>.env  (then fill in values)",
        "# To regenerate:  uv run python scripts/gen_env_examples.py",
    ]

    # Group fields by UI group
    groups: dict[str, list[tuple[str, Any]]] = {}
    for name, field in cls.model_fields.items():
        extra = field.json_schema_extra or {}
        if not isinstance(extra, dict):
            extra = {}
        group = extra.get("group", "General")
        groups.setdefault(group, []).append((name, field))

    for group_name, group_fields in groups.items():
        lines.append("")
        lines.append(f"# ── {group_name} ──")

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

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    env_dir = Path(__file__).resolve().parent.parent / "infra" / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    examples = [
        (env_dir / "tg-jenkins-bot.env.example", BotSettings, "Telegram Bot Config"),
        (env_dir / "agent-control.env.example", AgentSettings, "Agent Control Config"),
        (env_dir / "file-manager.env.example", StorageSettings, "File Manager Config"),
        (env_dir / "build-manager.env.example", BuildSettings, "Build Manager Config"),
        (env_dir / "config-hub.env.example", HubBootstrap, "Config Hub Infra"),
        (env_dir / "tg-admin-bot.env.example", AdminBotBootstrap, "Admin Bot Infra"),
    ]

    for path, cls, title in examples:
        path.write_text(_generate_example(cls, title))
        print(f"✓ Generated {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
