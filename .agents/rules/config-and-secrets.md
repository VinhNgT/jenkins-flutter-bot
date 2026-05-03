---
trigger: glob
globs: **/config*.py, **/app.py, **/.env*, **/docker-compose.yml, **/*.json
description: Configuration precedence, secret masking, deep merge, and frontend form patterns.
---

# Configuration & Secrets

Triggered when editing config-related files. Covers the configuration precedence chain, secret handling, and the config-ui frontend conventions.

---

## Config Precedence Chain

All services resolve configuration in the same strict order:

```
JSON Config File (Web UI)  >  Environment Variable  >  .env file  >  Hardcoded Default
```

Both `Config.resolve()` (tg-bot) and `AgentConfig.resolve()` (agent-control) implement this identically:

1. Check the JSON file at `CONFIG_PATH` for a dotted key (e.g., `"telegram.bot_token"`)
2. Fall back to the corresponding env var (e.g., `TELEGRAM_BOT_TOKEN`)
3. Fall back to `.env` file (loaded by `python-dotenv`)
4. Use the hardcoded default, or raise `KeyError` if `required=True`

Do not bypass this chain. If you need a new config value, add it through `resolve()` with all four layers.

---

## Config Files and Volumes

| File | Volume | Mount Path | Written By | Read By |
|------|--------|------------|------------|---------|
| `bot.json` | `bot-config` | `/config/bot/` | config-ui | tg-bot, config-ui |
| `agent.json` | `agent-config` | `/config/` | config-ui | agent-control, config-ui |
| `oauth.json` | `bot-config` | `/config/bot/` | config-ui (Drive OAuth) | tg-bot (DriveUploader) |

Both `config-ui` and `tg-bot` mount `bot-config` at `/config/bot/`, so `oauth.json` is accessible from both containers at the same path.

---

## Secret Masking

The config-ui masks sensitive fields before sending them to the browser:

- **Bot secrets**: `telegram.bot_token`, `jenkins.api_token`, `drive.client_secret`
- **Agent secrets**: `agent.secret`

The mask value is the literal string `"********"`. When saving, `_restore_masked_secrets()` checks: if the incoming value for a secret field equals `"********"`, the existing value is preserved. This prevents the mask from overwriting real secrets.

---

## Deep Merge on Save

Config saves use `_deep_merge()` for recursive dict merging. Sending `{"telegram": {"bot_token": "new"}}` updates only that key — all other fields in the JSON file are preserved.

This is critical for the config-ui workflow. Do not replace deep merge with a full overwrite.

---

## Frontend Form Convention

The config-ui `index.html` uses a naming convention for form inputs:

```html
<input name="bot:telegram.bot_token" />
<input name="agent:agent.secret" />
```

Format: `scope:dotted.key` where `scope` is `bot` or `agent`.

The `collectConfig()` JavaScript function splits on `:` to determine which config section the field belongs to, then uses `nestedSet()` to build the nested JSON payload. When adding new config fields to the UI, follow this same `scope:dotted.key` pattern on the input's `name` attribute.
