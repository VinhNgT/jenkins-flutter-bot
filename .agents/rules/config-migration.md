---
trigger: model_decision
description: When to write a config migration script, what it must do, and the invariants it must preserve.
---

# Config Migration Scripts

Loaded when schema changes require transforming existing JSON config files on disk. Covers when a migration is necessary and the constraints it must respect.

---

## When a Migration Script Is Needed

Not every schema change needs a migration. `ServiceSettings.load()` is tolerant of missing keys — it falls back through env vars and defaults when a key is absent from the JSON file. **Additive changes are free**: new fields with defaults simply resolve to their defaults on first boot.

A migration script is required only when:

| Change type | Why migration is needed |
|-------------|------------------------|
| **Key rename** | Existing data is stranded under the old key; the new key silently resolves to its default |
| **Structural reshape** (key moved to a different parent) | Dotted key lookups rely on exact paths; stale paths silently return `None` |
| **Value type change** | A stored string won't coerce correctly under the new field type |
| **Config scope change** (field moves between JSON files, e.g. `bot.json` → `storage.json`) | Data lives in the wrong file; the new schema reads from a different volume |

**Deletions and additions with sensible defaults do not need migration scripts.**

---

## Invariants the Script Must Preserve

- **Use `deep_merge()`, never a full overwrite** — a migration transforms specific keys; all untouched keys must be preserved.
- **Use `load_json` / `write_json` from `config_hub.config_store`** — they handle missing files gracefully and enforce consistent JSON formatting.
- **Do NOT touch bootstrap fields** — fields in `BootstrapSettings` subclasses live outside JSON config files (env-only). Never read from or write to `.env` files in a migration script.
- **Do NOT hard-code Docker volume paths** — accept paths from env vars or CLI args. The authoritative paths are in the compose files and `infra/` env templates.
- **Do NOT rely on `ServiceSettings.load()`** in the migration — it reads the new schema. The migration operates on raw JSON against the *old* structure.
- **Do NOT delete stale keys** — the config layer silently ignores unknown keys, so orphaned keys are harmless. Document the loss rather than surgically deleting.

---

## Script Placement and Naming

Place migration scripts in `scripts/`, named `migrate_<from_version>_to_<to_version>.py`. Run via `uv run scripts/migrate_*.py` from the repo root. Scripts must be idempotent — running twice produces the same result as running once.

---

## Config File Locations

Config paths are hardcoded in each service module. The authoritative mapping is:

| File | Service | Volume |
|------|---------|--------|
| `/app/data/bot.json` | tg-jenkins-bot | `bot-data` |
| `/app/data/agent.json` | agent-control | `agent-data` |
| `/app/data/storage.json` | file-manager | `storage-data` |
| `/app/data/builds.json` | build-manager | `build-manager-data` |

---

## When to Skip the Migration Entirely

If the old config doesn't have the field and the new default is correct for existing deployments, **document that the default was chosen for backward compatibility** in the field's description or help text. A migration script that only writes default values is wrong — `ServiceSettings.load()` already handles that.
