#!/usr/bin/env python3
"""Generate env/*.env.example files from schema declarations.

Usage:
    uv run python scripts/gen_env_examples.py

Requires ``uv sync`` so all workspace packages are importable.
"""

from __future__ import annotations

from pathlib import Path

from agent_control.schema import AGENT_FIELDS
from agent_control.schema import MODULE_TITLE as AGENT_TITLE
from config_schema import FieldDef
from tg_jenkins_bot.schema import BOT_FIELDS
from tg_jenkins_bot.schema import MODULE_TITLE as BOT_TITLE


def _generate_example(fields: tuple[FieldDef, ...], title: str) -> str:
    """Generate a self-documenting .env.example from FieldDef declarations."""
    lines: list[str] = [
        f"# {'─' * 50}",
        f"# {title}",
        f"# {'─' * 50}",
        "#",
        "# This example is generated from the schema definitions.",
        "# To use:  cp bot.env.example bot.env  (then fill in values)",
        "# To regenerate:  uv run python scripts/gen_env_examples.py",
    ]

    # Group fields
    groups: dict[str, list[FieldDef]] = {}
    for f in fields:
        if not f.env_var:
            continue
        groups.setdefault(f.group, []).append(f)

    for group_name, group_fields in groups.items():
        lines.append("")
        lines.append(f"# ── {group_name} ──")

        for f in group_fields:
            lines.append("")
            req_tag = " (required)" if f.required else ""
            lines.append(f"# {f.label}{req_tag}")
            if f.description:
                lines.append(f"# {f.description}")

            # Required fields are uncommented to signal they need filling.
            # Optional fields are commented out; show default if one exists.
            if f.required:
                lines.append(f"{f.env_var}=")
            elif f.default:
                lines.append(f"# {f.env_var}={f.default}")
            else:
                lines.append(f"# {f.env_var}=")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    env_dir = Path(__file__).resolve().parent.parent / "infra" / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    bot_example = env_dir / "bot.env.example"
    agent_example = env_dir / "agent.env.example"

    bot_example.write_text(_generate_example(BOT_FIELDS, BOT_TITLE))
    agent_example.write_text(_generate_example(AGENT_FIELDS, AGENT_TITLE))

    print(f"✓ Generated {bot_example.relative_to(Path.cwd())}")
    print(f"✓ Generated {agent_example.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
