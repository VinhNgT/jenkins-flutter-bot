"""Configuration core framework based on Pydantic.

Provides ``BootstrapSettings`` (env-only, hard crash),
``ServiceSettings`` (JSON > env, soft fail), UI adapter,
dict helpers, and config I/O utilities used by every service in the stack.

Security primitives:
  - ``redact`` / ``register_secret`` / ``install_log_redaction`` — secret scrubbing
  - ``setup_service_logging`` — standardised logging with auto-redaction
"""

from config_core.schema import (
    BootstrapSettings as BootstrapSettings,
    ServiceSettings as ServiceSettings,
    ConfigDocument as ConfigDocument,
    get_frontend_schema as get_frontend_schema,
    get_secret_keys as get_secret_keys,
    read_masked_config as read_masked_config,
    save_config_with_merge as save_config_with_merge,
    format_validation_error as format_validation_error,
    resolve_config_path as resolve_config_path,
)

from config_core.redact import (
    install_log_redaction as install_log_redaction,
    register_secret as register_secret,
    redact as redact,
)

from config_core.telegram import (
    verify_init_data as verify_init_data,
)

from config_core.logging import (
    setup_service_logging as setup_service_logging,
    get_buffer_logs as get_buffer_logs,
)
