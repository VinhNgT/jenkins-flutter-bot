---
trigger: glob
globs: **/config*.py, **/schema*.py, **/app.py, **/.env*, **/docker-compose.yml, **/*.json, **/schema-renderer.js, **/env_io.py, **/config_store.py
description: Declarative configuration schema, secret masking, deep merge, config transfer, and dynamic UI rendering.
---

# Configuration & Secrets

Triggered when editing config-related files. Covers the declarative schema system, configuration precedence chain, secret handling, and the stack-manager frontend conventions.

---

## Declarative Configuration Schema

Configuration is defined **declaratively** in per-module `schema.py` files. Each field is a `FieldDef` dataclass (defined in `config-schema` library) containing all metadata needed for resolution, UI rendering, and environment variable mapping.

### Schema Ownership

Each module owns its field declarations:

| Module | Declares | Config Class | Schema Endpoint |
|--------|----------|--------------|-----------------|
| `tg-bot` | `BOT_FIELDS` + `BOT_INFRA` | `Config` | `GET /control/schema` |
| `agent-control` | `AGENT_FIELDS` + `AGENT_INFRA` | `AgentConfig` | `GET /control/schema` |
| `stack-manager` | `DRIVE_FIELDS` + `DRIVE_INFRA` | — | `GET /api/config/schema` |

The shared `FieldDef` dataclass, `resolve_fields()`, and `serialize_schema()` live in `config_schema`.

### Adding a New Config Field

Add a `FieldDef` to the owning module's `schema.py` and the corresponding attribute to `config.py`. Everything else — UI rendering, help text, defaults, required markers, secret masking — is derived automatically from the schema.

### Schema Flow

```
schema.py (FieldDef declarations)
    → config.py (resolve_fields() → typed Config dataclass)
    → control.py (GET /control/schema → serialized JSON)
    → stack-manager (fetches schema via HTTP → schema-renderer.js renders forms)
```

---

## Partitioned Schema: Runtime vs Infrastructure

Each service's schema declares **two separate field tuples**: `*_FIELDS` (portable) and `*_INFRA` (environment-specific).

**Runtime fields** are portable — they travel with config exports/imports.

**Infrastructure fields** are environment-specific network plumbing (e.g., `JENKINS_URL`, `BOT_SERVICE_URL`). They are excluded from config exports and managed per deployment via `docker-compose.yml` or per-service `infra/env/*.env` files.

The `GET /control/schema` endpoint returns both partitions so consumers can handle them appropriately.

---

## Config Precedence Chain

All services resolve configuration in the same strict order:

```
JSON Config File (Web UI)  >  Environment Variable  >  .env file  >  Hardcoded Default
```

Resolution is **infallible** — it always returns a value, never raises. Validation of required fields is the responsibility of the manager classes (`BotManager`, `AgentManager`), not the config layer.

Do not bypass this chain. If you need a new config value, add a `FieldDef` to the owning module's `schema.py`.

---

## Config Files and Volumes

| File | Volume | Written By | Read By |
|------|--------|------------|---------|
| `bot.json` | `bot-config` | stack-manager | tg-bot, stack-manager |
| `agent.json` | `agent-config` | stack-manager | agent-control, stack-manager |
| `drive.json` | `drive-config` | stack-manager | stack-manager |
| `oauth.json` | `bot-config` | stack-manager (OAuth) | tg-bot (token reader) |

Drive OAuth credentials (`client_id`, `client_secret`) live in `drive.json`, not `bot.json`. The `oauth.json` token file is on `bot-config` so both `stack-manager` and `tg-bot` can access it at the same mount path. `tg-admin-bot` no longer mounts config volumes — it proxies all operations through the stack-manager API.

---

## Secret Masking

Secret fields are identified dynamically from the schema (`secret: True` on the `FieldDef`). The stack-manager strips secret values before sending to the browser and tracks which secrets are set (by character length). On save, `None`/empty secret fields are cleaned from the payload so `deep_merge()` preserves existing values.

---

## Deep Merge on Save

Config saves use `deep_merge()` for recursive dict merging. Sending `{"telegram": {"bot_token": "new"}}` updates only that key — all other fields are preserved.

This is critical for the stack-manager workflow. Do not replace deep merge with a full overwrite.

---

## Dynamic UI Rendering

The stack-manager renders forms dynamically from module schemas. It fetches schemas from services via HTTP, merges with its local drive schema, and `schema-renderer.js` generates form elements from the `FieldDef` metadata.

### Frontend Form Convention

Dynamic form inputs follow the `scope:dotted.key` naming convention (e.g., `bot:telegram.bot_token`, `drive:drive.client_id`). The scope prefix determines which config section the field belongs to when building the save payload.
