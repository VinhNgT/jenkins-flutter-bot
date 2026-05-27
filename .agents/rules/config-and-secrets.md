---
trigger: glob
description: Pydantic configuration system, secret masking, deep merge, config transfer, and dynamic UI rendering.
globs: **/config*.py, **/app.py, **/.env*, **/docker-compose.yml, **/*.json, **/schema-renderer.js, **/env_io.py, **/config_store.py
---

# Configuration & Secrets

Triggered when editing config-related files. Covers the Pydantic configuration system, precedence chain, secret handling, and the config-hub frontend conventions.

---

## Configuration Architecture

Two base classes from `config-core` partition configuration by lifecycle:

- **`BootstrapSettings`** — env-only, resolved once at process start. Hard crash if invalid. Used by services with no dashboard-editable state (`config-hub`).
- **`ServiceSettings`** — JSON > env, loaded on demand by managers. Soft fail → pending state. All fields are visible in the dashboard. Used by services that expose `/control/schema`.

### Schema Ownership

Each schema-owning service declares a `ServiceSettings` subclass and exposes it via `GET /control/schema`:

| Service | Config Class | Schema Endpoint |
|---------|-------------|-----------------|
| `tg-jenkins-bot` | `BotSettings` | `GET /control/schema` |
| `agent-control` | `AgentSettings` | `GET /control/schema` |
| `file-manager` | `StorageSettings` | `GET /control/schema` |
| `build-manager` | `BuildSettings` | `GET /control/schema` |

`config-hub` owns zero schemas — it fetches all schemas from the owning services via HTTP and proxies them to the frontend.

### Adding a New Config Field

Add a Pydantic `Field()` to the owning module's `config.py` `ServiceSettings` subclass. Everything else — UI rendering, help text, defaults, required markers, secret masking — is derived automatically from the field's `json_schema_extra` metadata.

### Schema Flow

```
config.py (ServiceSettings subclass with Field() declarations)
    → routers/control.py (GET /control/schema → serialized JSON)
    → config-hub (fetches schemas from all services → schema-renderer.js renders forms)
```

---

## Config Precedence Chain

**`ServiceSettings`** (dashboard-editable) resolves in strict order:

```
JSON Config File (Web UI)  >  Environment Variable  >  .env file  >  Default
```

**`BootstrapSettings`** (env-only) resolves:

```
Environment Variable  >  .env file  >  Default
```

Both classes raise `ValidationError` if required fields (fields with no default) are missing. For `BootstrapSettings` this is a hard crash at process start. For `ServiceSettings` the error is caught by the manager, which enters a pending state — the control API stays up for retries.

Do not bypass these chains. Use `.load()` — never read env vars or JSON directly in business logic.

---

## Config Files and Volumes

Each service stores its own config in a dedicated volume. Config paths are **hardcoded** within each module — no path configuration is needed or supported.

| File | Volume | Written By | Read By |
|------|--------|------------|---------|
| `/app/data/bot.json` | `bot-data` | config-hub (via PUT /control/config) | `tg-jenkins-bot` |
| `/app/data/agent.json` | `agent-data` | config-hub (via PUT /control/config) | agent-control |
| `/app/data/storage.json` | `storage-data` | config-hub (via PUT /control/config) | file-manager |
| `/app/data/builds.json` | `build-manager-data` | config-hub (via PUT /control/config) | build-manager |

No service mounts another service's volume. All config I/O crosses service boundaries via HTTP (`/control/config`).

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

Dynamic form inputs follow the `scope:dotted.key` naming convention (e.g., `bot:telegram.bot_token`, `file_manager:drive.client_id`). The scope prefix determines which config section the field belongs to when building the save payload. See `communication-flows.md` for the scope-to-service translation.
