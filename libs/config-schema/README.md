# 📋 Config Schema

A shared workspace library providing the declarative configuration schema framework used by all services in the Jenkins Flutter Bot ecosystem.

## What It Provides

- **`FieldDef`** — Frozen dataclass declaring a configuration field: JSON key, env var name, default, label, description, help text, secret/required flags, field type, and value type.
- **`resolve_fields()`** — Resolves a tuple of `FieldDef`s against the config precedence chain: `JSON > Env Var > .env file > Default`. Returns a dict of resolved values.
- **`serialize_schema()`** — Serializes field tuples to JSON for the `/control/schema` API endpoint.
- **`nested_get()`** — Reads dotted keys from nested dicts (e.g., `telegram.bot_token` → `data["telegram"]["bot_token"]`).

## Usage

All apps depend on this library. To add a new config field to any service, add a `FieldDef` to that service's `schema.py` — everything else (UI rendering, env var mapping, defaults) is derived automatically.

```python
from config_schema import FieldDef, resolve_fields, serialize_schema
```
