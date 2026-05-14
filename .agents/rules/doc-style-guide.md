---
trigger: glob
globs: "**/.agents/rules/*.md, **/README.md"
description: MUST read before creating or editing any documentation, rule files, or READMEs. Defines the principles for writing durable, useful agent guidelines.
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

## What Makes a Good Rule File

### 1. Stable Over Time

A good rule file should remain accurate for months, not days. Before writing a section, ask: *"Will this still be true after the next three feature PRs?"*

**Durable content:**
- Architectural boundaries ("the bot never initiates OAuth")
- Design patterns ("all services use the same config precedence chain")
- Naming conventions ("kebab-case directories, snake_case packages")
- Hard constraints ("never mount docker.sock")

**Fragile content (avoid):**
- Exact line numbers or function signatures
- Complete config field lists (they grow constantly)
- Specific HTTP response shapes (read the code)
- Package version numbers

### 2. Structural, Not Exhaustive

Describe the *shape* of things, not every instance. For example:

> **Good:** "Each service's `config.py` declares a `ServiceSettings` subclass with fields tagged as portable or infrastructure."

> **Bad:** "BOT_FIELDS contains 12 entries: telegram.bot_token, telegram.allowed_chat_ids, telegram.admin_contact, ..."

The first sentence stays accurate when fields are added. The second is instantly stale.

### 3. Constraint-Oriented

The highest-value content in a guide is the list of things an agent must NOT do. Constraints prevent expensive mistakes. State them clearly and explain the rationale:

> **Do NOT expose bot or agent ports to the host** — only `jenkins:8080` and `config-hub:9000` are host-facing.

The constraint is the rule. The explanation prevents the agent from "helpfully" overriding it.

### 4. Grounded in Architecture

Every statement should be traceable to an architectural decision. If a rule exists only because "we've always done it this way," either find the architectural reason or remove the rule.

---

## File Organization

### One Concern Per File

Each rule file covers a single concern domain:

| File | Concern |
|------|---------|
| `general-guide.md` | Project identity, repo layout, service topology, hard constraints |
| `coding-conventions.md` | Language, tooling, project structure patterns |
| `config-and-secrets.md` | Schema system, precedence chain, secret masking |
| `docker-and-infra.md` | Containers, volumes, networking, CI/CD pipeline |
| `communication-flows.md` | Service-to-service protocols, OAuth, build flow |
| `doc-style-guide.md` | Meta-guide — how to write and maintain rule files |

### Trigger Metadata

Every file starts with a YAML frontmatter block:

```yaml
---
trigger: always_on | glob | model_decision
globs: **/*.py                              # only for trigger: glob
description: One-line summary of when this file is relevant.
---
```

- **`always_on`** — loaded on every interaction (use sparingly — only for `general-guide.md`)
- **`glob`** — loaded when files matching the glob pattern are edited (by user or agent)
- **`model_decision`** — loaded at the model's discretion based on the task context

### Cross-References

Use prose references to other rule files rather than duplicating content:

> "For the config precedence chain, see `config-and-secrets.md`."

Duplication creates drift. If the same fact appears in two files, it will eventually be updated in one and not the other.

---

## Anti-Patterns

### 1. Tutorial-Style Walkthroughs

❌ "First, open `config.py`. Then add a `Field()` with the right metadata. Then open `routers/control.py` and wire it up..."

✅ "To add a new config field, add a Pydantic `Field()` to the owning module's `config.py`. Everything else — UI rendering, env var mapping, defaults — is derived automatically."

The second version tells the agent *what to do* without prescribing *exactly how*, which lets it adapt to the current state of the code.

### 2. Snapshot Documentation

❌ Copying an entire `docker-compose.yml` into a rule file.

✅ Describing the service topology and volume layout as a table.

The compose file changes frequently. The topology changes rarely.

### 3. Redundant with Code

If something is already expressed clearly in code (type hints, docstrings, variable names), don't repeat it in a rule file. Rule files should cover the *implicit* knowledge — the things you'd explain to a new team member that aren't obvious from reading the code.

### 4. Mixing Levels of Abstraction

Don't put "what is this project" and "how to parse webhook JSON" in the same section. Use separate files for high-level architecture and low-level protocol details, with clear triggers so the model loads only what it needs.

---

## Maintenance Checklist

When making significant architectural changes, review rule files for staleness:

1. **Service count** — did you add or remove a service? Update `general-guide.md` topology.
2. **Volume layout** — did you rename or add volumes? Update `docker-and-infra.md`.
3. **Shared libraries** — did you extract or rename a library? Update `coding-conventions.md` and `general-guide.md`.
4. **Config scopes** — did you rename or add a config scope? Update `config-and-secrets.md`.
5. **Communication patterns** — did you add a new service-to-service flow? Update `communication-flows.md`.
6. **Hard constraints** — did you establish a new boundary? Add it to `general-guide.md`.

The rule files are the **last thing updated** in an architectural change — after the code is working and verified.
