---
trigger: glob
globs: "**/config*.py, **/app.py, **/.env*, **/docker-compose.yml, **/*.json, **/schema-renderer.js, **/env_io.py, **/config_store.py"
description: Pydantic configuration system, secret masking, deep merge, config transfer, and dynamic UI rendering.
---

# Configuration & Secrets

Triggered when editing config-related files. Covers the Pydantic configuration system, precedence chain, secret handling, and the config-hub frontend conventions.

---

## Configuration Architecture

All services use `ServiceSettings` (from `config-core`) as the base class for their configuration. Each service's `config.py` declares a `ServiceSettings` subclass with Pydantic fields.

### Schema Ownership

Each service owns its field declarations and exposes them via `GET /control/schema`:

| Service | Config Class | Schema Endpoint |
|---------|-------------|-----------------|
| `tg-bot` | `BotConfig` | `GET /control/schema` |
| `agent-control` | `AgentConfig` | `GET /control/schema` |
| `file-manager` | `StorageConfig` | `GET /control/schema` |
| `build-manager` | `BuildConfig` | `GET /control/schema` |

`config-hub` owns zero schemas — it fetches all schemas from the owning services via HTTP and proxies them to the frontend. `tg-admin-bot` has no schema or control API — all its fields are infrastructure-only.

### Adding a New Config Field

Add a Pydantic `Field()` to the owning module's `config.py` `ServiceSettings` subclass. Everything else — UI rendering, help text, defaults, required markers, secret masking — is derived automatically from the field's `json_schema_extra` metadata.

### Schema Flow

```
config.py (ServiceSettings subclass with Field() declarations)
    → routers/control.py (GET /control/schema → serialized JSON)
    → config-hub (fetches schemas from all services → schema-renderer.js renders forms)
```

---

## Partitioned Schema: Runtime vs Infrastructure

Each service's `ServiceSettings` subclass uses `json_schema_extra` to tag fields:

- **Runtime fields** (no tag or `infra: False`) — portable, travel with config exports/imports.
- **Infrastructure fields** (`infra: True`) — environment-specific network plumbing (e.g., `JENKINS_URL`, `SELF_URL`, `FILE_MANAGER_URL`). Excluded from config exports, managed per deployment via `docker-compose.yml` or `infra/env/*.env` files.

The `GET /control/schema` endpoint returns both partitions so consumers can handle them appropriately.

---

## Config Precedence Chain

All services resolve configuration in the same strict order:

```
JSON Config File (Web UI)  >  Environment Variable  >  .env file  >  Hardcoded Default
```

Resolution is **infallible** — it always returns a value, never raises. Validation of required fields is the responsibility of the manager classes, not the config layer.

Do not bypass this chain. Use `ServiceSettings.load()` — never read env vars or JSON directly in business logic.

---

## Config Files and Volumes

Each service stores its own config in a dedicated volume. Config paths are **hardcoded** within each module — no path configuration is needed or supported.

| File | Volume | Written By | Read By |
|------|--------|------------|---------|
| `/app/data/bot.json` | `bot-data` | config-hub (via PUT /control/config) | tg-bot |
| `/app/data/agent.json` | `agent-data` | config-hub (via PUT /control/config) | agent-control |
| `/app/data/storage.json` | `storage-data` | config-hub (via PUT /control/config) | file-manager |
| `/app/data/builds.json` | `build-manager-data` | config-hub (via PUT /control/config) | build-manager |

No service mounts another service's volume. All config I/O crosses service boundaries via HTTP (`/control/config`). `tg-admin-bot` mounts no volumes — it proxies all operations through the config-hub API.

OAuth tokens are stored separately by file-manager in its own data volume and are **not** part of config exports.

---

## Secret Masking

Secret fields are identified via `json_schema_extra={"secret": True}` on the Pydantic field. The config-hub strips secret values before sending to the browser and tracks which secrets are set (by character length). On save, `None`/empty secret fields are cleaned from the payload so `deep_merge()` preserves existing values.

---

## Deep Merge on Save

Config saves use `deep_merge()` for recursive dict merging. Sending `{"telegram": {"bot_token": "new"}}` updates only that key — all other fields are preserved.

This is critical for the config-hub workflow. Do not replace deep merge with a full overwrite.

---

## Dynamic UI Rendering

The config-hub renders forms dynamically from service schemas. It fetches schemas from all four owning services via HTTP and `schema-renderer.js` generates form elements from the field metadata.

### Frontend Form Convention

Dynamic form inputs follow the `scope:dotted.key` naming convention (e.g., `bot:telegram.bot_token`, `drive:drive.client_id`). The scope prefix determines which config section the field belongs to when building the save payload. See `communication-flows.md` for the scope-to-service translation.
