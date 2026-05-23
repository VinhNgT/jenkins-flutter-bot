# config-core

Shared workspace library providing the Pydantic-based configuration framework used by all microservices in the Jenkins Flutter Bot ecosystem.

## What It Provides

- **`BootstrapSettings`** — Pydantic `BaseSettings` subclass for env-only config resolved once at process start. Hard crash if required fields are missing. Used by services with no dashboard-editable state (`config-hub`).
- **`ServiceSettings`** — Pydantic `BaseSettings` subclass with JSON > Env precedence. Loaded on demand by service managers; raises `ValidationError` on missing required fields (caught by managers for soft fail). All fields are visible in the config-hub dashboard.
- **`get_frontend_schema()`** — Adapter to convert a Pydantic model's fields into the config-hub UI schema format.
- **`ConfigDocument`** — Object-oriented wrapper for nested dict manipulation (dotted-key get/set, deep merge).
- **`get_secret_keys()`** — Returns the set of field names marked as secrets for a given settings subclass.
- **`read_masked_config()`** — Reads a service's JSON config file and masks secret field values before returning.
- **`save_config_with_merge()`** — Deep-merges a config payload into the existing JSON file, preserving untouched keys.

## Usage

All apps depend on this library. To add a new config field to any service, add a Pydantic `Field()` to that service's `config.py` `ServiceSettings` subclass — everything else (UI rendering, env var mapping, defaults, secret masking) is derived automatically from the field's `json_schema_extra` metadata.

```python
from config_core import BootstrapSettings, ServiceSettings, get_frontend_schema
```
