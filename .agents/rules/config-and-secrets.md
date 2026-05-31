---
trigger: glob
description: Pydantic configuration schemas, secret masking, dual-auth paradigm, and JSON configuration migrations.
globs: **/config*.py, **/app.py, **/.env*, **/docker-compose.yml, **/*.json, **/SchemaForm.tsx, **/env_io.py, **/config_store.py, **/*migration*.py, **/migrate*.py
---

# Configuration & Secrets

Triggered when editing config-related files. Outlines the unified schema system, storage boundaries, dynamic UI flows, dual-auth administrative security, and schema transformation migrations.

---

## 1. Schema System & Storage Bounds
- **Pydantic Separation**:
  - `BootstrapSettings`: Env-only settings, resolved at startup. Crashes if invalid (used by non-configurable services like `config-hub`).
  - `ServiceSettings`: Schema-driven JSON > Env configuration. soft-fails to pending states to keep API responsive for remote adjustments.
- **Dotted-Key Schema Conversion**: Config options map to JSON via `get_frontend_schema()`. Dynamic UI forms are derived entirely from field metadata.
- **Deep Merge on Save**: Config updates are recursively deep-merged. Saving a partial payload preserves untouched JSON keys. Do not implement destructive overwrites.

---

## 2. Secrets & Log Redaction
- **Masking at Rest & Transit**: Mark fields with `json_schema_extra={"secret": True}` to automatically mask values in transient logs and prevent exposing raw secrets to client web browsers.
- **Automatic Scrubbing**: Secrets must be dynamically registered at startup (`register_secret()`) to let the shared `config-core` logging filter automatically redact secret keys from system stdout logs.

---

## 3. Dual-Authentication Paradigm
Config Hub implements a strict security boundary using two authentication vectors:
1. **Primary Authentication (Telegram WebApp initData)**: Visitor sessions are validated cryptographically on the backend using HMAC-SHA256 signature verification against the Telegram `InitData` header. Whitelisted admin Telegram IDs grant dashboard access.
2. **Fallback Authentication (HTTP Basic Auth)**: Reserved strictly for local/LAN setups.
3. **Gateway Strip Constraint**: To prevent credential brute-forcing, Caddy must systematically strip the `Authorization` header from all incoming non-LAN public ingress traffic. Google Drive OAuth redirect callbacks (`/api/webapp-admin/drive/oauth/callback`) are exempted to permit external accounts redirects.

---

## 4. Configuration Migration
Triggered when schema renames, value coercions, or config scope transitions require rewriting stored configurations at rest.
- **Trigger Conditions**: A migration script is strictly required when key renames would orphan stored keys, structural reshaping moves nested structures to different parent trees, configuration keys migrate between microservice bounds (e.g. `bot.json` to `storage.json`), or value types mutate in a way that breaks standard Pydantic type coercions.
- **Isolate Docker Volume Paths**: Do not hard-code absolute host paths. Migration scripts must derive file targets dynamically from standardized environment variables.
- **Avoid Schema Version Coupling**: Operate directly on raw JSON dict models. Do not import `ServiceSettings` classes directly during migrations since they reflect the *new* target schemas, not the *old* source states.
- **Idempotency**: All migration scripts must yield identical states if executed repeatedly.

