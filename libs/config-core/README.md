# config-core

Shared workspace library providing the Pydantic-based configuration framework used by all microservices in the Jenkins Flutter Bot ecosystem.

## What It Provides

- **`ServiceSettings`** — Pydantic `BaseSettings` subclass. The base class for all service configurations. Provides the standard config precedence chain: `JSON Config File > Env Var > .env file > Default`. Call `ServiceSettings.load()` to resolve configuration.
- **`FieldDef`** — Frozen dataclass declaring a configuration field's metadata for schema serialization and UI rendering (label, description, help text, secret/required flags, type).
- **`resolve_fields()`** — Resolves a tuple of `FieldDef`s against the config precedence chain. Returns a dict of resolved values.
- **`serialize_schema()`** — Serializes field metadata to JSON for the `/control/schema` API endpoint consumed by config-hub.
- **`nested_get()`** — Reads dotted keys from nested dicts (e.g., `telegram.bot_token` → `data["telegram"]["bot_token"]`).
- **`get_secret_keys()`** — Returns the set of field names marked as secrets for a given `ServiceSettings` subclass.
- **`read_masked_config()`** — Reads a service's JSON config file and masks secret field values before returning.
- **`save_config_with_merge()`** — Deep-merges a config payload into the existing JSON file, preserving untouched keys.

## Usage

All apps depend on this library. To add a new config field to any service, add a Pydantic `Field()` to that service's `config.py` `ServiceSettings` subclass — everything else (UI rendering, env var mapping, defaults, secret masking) is derived automatically from the field's `json_schema_extra` metadata.

```python
from config_core import ServiceSettings, FieldDef, resolve_fields, serialize_schema
```
