---
trigger: glob
globs: **/config*.py, **/schema*.py, **/app.py, **/.env*, **/docker-compose.yml, **/*.json, **/schema-renderer.js
description: Declarative configuration schema, secret masking, deep merge, and dynamic UI rendering.
---

# Configuration & Secrets

Triggered when editing config-related files. Covers the declarative schema system, configuration precedence chain, secret handling, and the config-ui frontend conventions.

---

## Declarative Configuration Schema

Configuration is defined **declaratively** in per-module `schema.py` files. Each field is a `FieldDef` dataclass (defined in `libs/config-schema/`) containing all metadata: JSON key, env var, default, label, description, help text, secret/required flags, field type, and value type.

### Key Files

| Module | Schema File | Config File | Schema Endpoint |
|--------|------------|-------------|-----------------|
| shared | `config_schema/schema.py` | — | — |
| `tg-bot` | `tg_jenkins_bot/schema.py` | `tg_jenkins_bot/config.py` | `GET /control/schema` |
| `agent-control` | `agent_control/schema.py` | `agent_control/config.py` | `GET /control/schema` |
| `config-ui` | `config_ui/schema.py` | — (config-ui only reads/writes JSON) | `GET /api/config/schema` |

### Adding a New Config Field

To add a new config field, you only need to edit **one file** — the owning module's `schema.py`:

1. Add a `FieldDef` entry to the module's field tuple (`BOT_FIELDS`, `AGENT_FIELDS`, or `UI_FIELDS`)
2. Add the corresponding attribute to the module's `Config` / `AgentConfig` dataclass in `config.py`

Everything else — UI rendering, help text, defaults, required markers, secret masking — is derived automatically from the schema.

### Schema Flow

```
schema.py (FieldDef declarations)
    → config.py (resolve_fields() → typed Config dataclass)
    → control.py (GET /control/schema → serialized JSON)
    → config-ui (fetches schema via HTTP → schema-renderer.js renders forms)
```

### `resolve_fields()` and `_coerce()`

`resolve_fields(fields, config_path)` and `_coerce()` live in `libs/config-schema/src/config_schema/schema.py`. All modules import them from `config_schema`. Values are automatically coerced to their declared `value_type` (`str`, `int`, `bool`, `list[int]`) via the `_coerce()` helper.

### `post_resolve()` (bot only)

The bot module has a `post_resolve()` hook for business logic that can't be expressed declaratively: `app_name` fallback chain, `job_id` defaulting to `job_name`, and `oauth_token_path` derivation.

---

## Config Precedence Chain

All services resolve configuration in the same strict order:

```
JSON Config File (Web UI)  >  Environment Variable  >  .env file  >  Hardcoded Default
```

Both `Config.resolve()` (tg-bot) and `AgentConfig.resolve()` (agent-control) delegate to `resolve_fields()` from `config_schema`, which implements this chain:

1. Check the JSON file at `CONFIG_PATH` for a dotted key (e.g., `"telegram.bot_token"`)
2. Fall back to the corresponding env var (e.g., `TELEGRAM_BOT_TOKEN`)
3. Fall back to `.env` file (loaded by `python-dotenv`)
4. Use the hardcoded default from the `FieldDef`

Resolution is **infallible** — it always returns a value, never raises. Validation of required fields is the responsibility of the manager classes (`BotManager`, `AgentManager`), not the config layer.

Do not bypass this chain. If you need a new config value, add a `FieldDef` to the owning module's `schema.py`.

---

## Config Files and Volumes

| File | Volume | Mount Path | Written By | Read By |
|------|--------|------------|------------|---------|
| `bot.json` | `bot-config` | `/config/bot/` | config-ui | tg-bot, config-ui |
| `agent.json` | `agent-config` | `/config/agent/` | config-ui | agent-control, config-ui |
| `ui.json` | `ui-config` | `/config/ui/` | config-ui | config-ui |
| `oauth.json` | `bot-config` | `/config/bot/` | config-ui (Drive OAuth) | tg-bot (DriveUploader) |

Both `config-ui` and `tg-bot` mount `bot-config` at `/config/bot/`, so `oauth.json` is accessible from both containers at the same path. Drive OAuth credentials (`client_id`, `client_secret`) live in `ui.json`, not `bot.json`.

---

## Secret Masking

Secret fields are identified dynamically from the schema (`secret: True` on the `FieldDef`). The config-ui:

1. Fetches schemas from bot/agent services via `ServiceClient.schema()`
2. Extracts secret field keys with `extract_secret_fields(schema)`
3. Strips secret values before sending to the browser (replaced with `None`)
4. Tracks which secrets are set via `secrets_set()` (returns character length or `False`)

When saving, `clean_secrets_from_payload()` removes `None`/empty secret fields from the incoming payload — `deep_merge()` then preserves existing values.

---

## Deep Merge on Save

Config saves use `deep_merge()` for recursive dict merging. Sending `{"telegram": {"bot_token": "new"}}` updates only that key — all other fields in the JSON file are preserved.

This is critical for the config-ui workflow. Do not replace deep merge with a full overwrite.

---

## Dynamic UI Rendering

The config-ui renders forms dynamically from module schemas:

1. `main.js` calls `API.getSchema()` → `GET /api/config/schema`
2. Config-ui aggregates schemas: fetches bot/agent via HTTP, merges with local UI schema
3. `schema-renderer.js` calls `renderSchemaForm()` for each scope
4. Each `FieldDef` generates: label, description, help button (if `help_html`), required marker, and the appropriate input element (text/password/number/select)
5. Save/reload buttons use `data-save` / `data-reload` data attributes with event delegation

### Frontend Form Convention

Dynamic form inputs follow the `scope:dotted.key` naming convention:

```html
<input name="bot:telegram.bot_token" />
<input name="agent:agent.secret" />
<input name="ui:drive.client_id" />
```

Format: `scope:dotted.key` where `scope` is `bot`, `agent`, or `ui`.

The `collectScope()` JavaScript function splits on `:` to determine which config section the field belongs to, then uses `nestedSet()` to build the nested JSON payload.
