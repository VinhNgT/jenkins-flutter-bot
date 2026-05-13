#!/usr/bin/env python3
"""Generate env/*.env.example files from schema declarations.

Usage:
    uv run python scripts/gen_env_examples.py

Requires ``uv sync`` so all workspace packages are importable.
"""

from __future__ import annotations

from pathlib import Path

from agent_control.schema import registry as agent_registry
from file_manager.schema import registry as storage_registry
from tg_jenkins_bot.schema import registry as bot_registry
from config_schema import RuntimeFieldDef, InfraFieldDef, ConfigRegistry


def _generate_example(registry: ConfigRegistry) -> str:
    """Generate a self-documenting .env.example from FieldDef declarations.

    Portable fields are emitted first with their defaults.
    Infrastructure-only fields are appended in a separate section,
    always commented out and always empty — they document all possible
    env vars the container accepts.
    """
    lines: list[str] = [
        f"# {'─' * 50}",
        f"# {registry.title}",
        f"# {'─' * 50}",
        "#",
        "# This example is generated from the schema definitions.",
        "# To use:  cp <name>.env.example <name>.env  (then fill in values)",
        "# To regenerate:  uv run python scripts/gen_env_examples.py",
    ]

    # Group portable fields by UI group
    portable: dict[str, list[RuntimeFieldDef]] = {}
    for f in registry.runtime_fields:
        if not f.env_var:
            continue
        portable.setdefault(f.group, []).append(f)

    # Group infra fields by UI group
    infra: dict[str, list[InfraFieldDef]] = {}
    for f_infra in registry.infra_fields:
        if not f_infra.env_var:
            continue
        infra.setdefault(f_infra.group, []).append(f_infra)

    # --- Portable fields ---
    for group_name, group_fields in portable.items():
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

    # --- Infrastructure fields ---
    if infra:
        lines.append("")
        lines.append(f"# {'─' * 50}")
        lines.append("# Infrastructure (environment-specific, not portable)")
        lines.append("# These settings are tied to your deployment topology.")
        lines.append("# Prefer docker-compose `environment:` section; .env is also acceptable.")
        lines.append(f"# {'─' * 50}")

        for group_name, infra_group_fields in infra.items():
            lines.append("")
            lines.append(f"# ── {group_name} ──")

            for f_infra in infra_group_fields:
                lines.append("")
                req_tag = " (required)" if f_infra.required else ""
                lines.append(f"# {f_infra.label}{req_tag}")
                if f_infra.description:
                    lines.append(f"# {f_infra.description}")
                if f_infra.default:
                    lines.append(f"# Default: {f_infra.default}")
                lines.append(f"# {f_infra.env_var}=")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    env_dir = Path(__file__).resolve().parent.parent / "infra" / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    examples = [
        (env_dir / "bot.env.example", bot_registry),
        (env_dir / "agent.env.example", agent_registry),
        (env_dir / "storage.env.example", storage_registry),
    ]

    for path, reg in examples:
        path.write_text(_generate_example(reg))
        print(f"✓ Generated {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
