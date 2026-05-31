---
trigger: glob
description: MUST read before creating or editing any documentation, rule files, or READMEs. Defines the principles for writing durable, useful agent guidelines.
globs: **/.agents/rules/*.md, **/README.md
---

# Doc Style Guide

Read this before creating or editing any `.agents/rules/` file or `README.md`. Defines the principles and anti-patterns for writing durable, useful documentation.

---

## Core Principle

**Document the why and the architecture, not the how of specific features.**

Agent guidelines exist to give an AI assistant the *mental model* it needs to make correct decisions autonomously. They should convey:

- What the system is and what it is not
- How services relate to each other
- What boundaries must never be crossed
- Where the authoritative source of truth lives for each concern

They should NOT convey:

- Step-by-step implementation of a single feature (use code comments instead)
- Exact file contents or API response bodies (read the code)
- Version-pinned dependency lists that change with every lockfile update

---

## Agent Contributions

The AI agent is authorized and encouraged to update codebase documentation, READMEs, and AI guides to maintain alignment with codebase changes, following standard workflows.

---

## Additional Hard Constraints

- **Single Mermaid Source of Truth**: Only the main root `README.md` is authorized to contain the Mermaid system topology graph. Sub-guides must NEVER contain duplicate Mermaid graphs to avoid documentation drift.
- **Code Comments for Low-Level Rules**: Highly specific code rules, function signatures, class interfaces, local constraints, and implementation details must be placed in the code itself as standard code comments, keeping sub-guides highly compacted and focused strictly on high-level design principles.

---

## What Makes a Good Rule File

### 1. Stable Over Time
A good rule file should remain accurate for months, not days. Before writing a section, ask: *"Will this still be true after the next three feature PRs?"*
- **Durable content**: Architectural boundaries, design patterns, naming conventions, and hard constraints.
- **Fragile content (avoid)**: Line numbers, complete config field lists, specific HTTP response shapes, and package versions.

### 2. Structural, Not Exhaustive
Describe the *shape* of things, not every instance. For example, specify that each service's `config.py` inherits from `ServiceSettings`, not a list of all fields.

### 3. Constraint-Oriented
The highest-value content in a guide is the list of things an agent must NOT do. State them clearly and explain the rationale.

---

## File Organization

### One Concern Per File

Each rule file covers a single concern domain:

| File | Concern |
|------|---------|
| `general-guide.md` | Project identity, repo layout, service topology, hard constraints |
| `personality-guide.md` | Identity, ownership mindset, stepping back, and declining instructions |
| `python-conventions.md` | Python conventions, Bigger Applications layout, dependency injection |
| `web-conventions.md` | Pure Preact stack, Telegram design language, stack-based navigation |
| `config-and-secrets.md` | Schema system, secret masking, dual-auth paradigm, and configuration migrations |
| `docker-and-infra.md` | Mock-first local dev, compose profiles, container rebuild, Windows bash usage |
| `testing-conventions.md` | Hermetic test isolation, pytest mocking, Vitest JSDOM environment |
| `communication-flows.md` | Build trigger pipeline, aggregated SSE streams, Google Drive OAuth |
| `doc-style-guide.md` | Meta-guide — how to write and maintain rule files |

### Trigger Metadata
Every file starts with a YAML frontmatter block defining the trigger mode (`always_on`, `glob`, or `model_decision`), path globs, and a short description.
