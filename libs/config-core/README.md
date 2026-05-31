# config-core

Shared workspace library providing the Pydantic-based configuration framework used by all microservices in the Jenkins Telegram Bot ecosystem.

## What It Provides

### Configuration Framework
- **`BootstrapSettings`** — Pydantic `BaseSettings` subclass for env-only config resolved once at process start. Hard crash if required fields are missing. Used by services with no dashboard-editable state (`service-hub`).
- **`ServiceSettings`** — Pydantic `BaseSettings` subclass with JSON > Env precedence. Loaded on demand by service managers; raises `ValidationError` on missing required fields (caught by managers for soft fail). All fields are visible in the service-hub dashboard.
- **`get_frontend_schema()`** — Adapter to convert a Pydantic model's fields into the service-hub UI schema format.
- **`ConfigDocument`** — Object-oriented wrapper for nested dict manipulation (dotted-key get/set, deep merge).
- **`get_secret_keys()`** — Returns the set of field names marked as secrets for a given settings subclass.
- **`read_masked_config()`** — Reads a service's JSON config file and masks secret field values before returning.
- **`save_config_with_merge()`** — Deep-merges a config payload into the existing JSON file, preserving untouched keys.

### Security, Telegram & Logging Primitives
- **`verify_service_token()`** — FastAPI dependency for inter-service bearer token authentication. Validates the `Authorization` header against `SERVICE_AUTH_TOKEN`.
- **`get_service_auth_headers()`** — Returns headers for outbound httpx clients.
- **`verify_init_data()`** — Cryptographically verifies Telegram Mini App `initData` payloads using HMAC-SHA256 signature verification.
- **`register_secret()`** — Registers a secret value for automatic log redaction.
- **`install_log_redaction()`** — Installs a logging filter that scrubs all registered secrets from log output.
- **`setup_service_logging()`** — Standardised logging setup with auto-redaction. Called once in each service's entry point.
- **`get_buffer_logs()`** — Retrieves standard in-memory buffered log records for real-time diagnostic output.

## Usage

All apps depend on this library. To add a new config field to any service, add a Pydantic `Field()` to that service's `config.py` `ServiceSettings` subclass — everything else (UI rendering, env var mapping, defaults, secret masking) is derived automatically from the field's `json_schema_extra` metadata.

```python
from config_core import BootstrapSettings, ServiceSettings, get_frontend_schema
from config_core.auth import verify_service_token, get_service_auth_headers
from config_core.logging import setup_service_logging, get_buffer_logs
from config_core.telegram import verify_init_data
```
