# 🔩 Stack Manager

A shared workspace library providing operational utilities for the Jenkins Flutter Bot stack. Used by `config-ui` and `tg-admin-bot` for service control, Drive OAuth, configuration I/O, and Jenkinsfile generation.

## What It Provides

| Module | Purpose |
|--------|---------|
| `services` | `ServiceClient` — HTTP proxy for bot/agent control APIs (start/stop/restart/status/schema) |
| `drive` | `DriveOAuth` — Google Drive OAuth flows (browser-redirect + headless code-paste) |
| `config_store` | JSON config I/O, secret field extraction, default value extraction |
| `env_io` | `.env` file generation, tarball export/import for config transfer |
| `jenkins_pipeline` | Jenkinsfile template generation from current configuration |

## Usage

```python
from stack_manager import ServiceClient, DriveOAuth, build_export_tarball, import_tarball
```

Both `config-ui` and `tg-admin-bot` depend on this library. It consolidates all shared operational logic so neither app duplicates service control, OAuth flows, or config I/O.
