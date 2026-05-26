"""Inter-service bearer token authentication.

Defence-in-depth for internal ``/control/*`` and ``/api/*`` endpoints.
When ``SERVICE_AUTH_TOKEN`` is set in the environment, all inter-service
calls must include it as a ``Bearer`` token in the ``Authorization``
header.  When unset, auth is bypassed (dev/test mode).

Inbound side (FastAPI dependency)::

    from config_core import verify_service_token
    app = FastAPI(dependencies=[Depends(verify_service_token)])

Outbound side (httpx client headers)::

    from config_core import get_service_auth_headers
    client = httpx.AsyncClient(headers=get_service_auth_headers())
"""

from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException, Request, status

# Read once at import time — the token never changes during a process lifetime.
_TOKEN = os.environ.get("SERVICE_AUTH_TOKEN", "")


async def verify_service_token(request: Request) -> None:
    """FastAPI dependency that validates the inter-service bearer token.

    Add to routers or apps via ``dependencies=[Depends(verify_service_token)]``.

    Behaviour:
      - Token not configured (empty) → pass through (dev/test mode)
      - Token configured, valid header → pass through
      - Token configured, missing/invalid → 401/403
    """
    if not _TOKEN:
        return  # Not configured — dev/test mode

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing service token",
        )

    if not secrets.compare_digest(auth[7:], _TOKEN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid service token",
        )


def get_service_auth_headers() -> dict[str, str]:
    """Return HTTP headers containing the service auth token.

    Used by HTTP clients (``ServiceClient``, ``BuildClient``, etc.)
    to authenticate when calling other services.  Returns an empty
    dict when no token is configured (dev/test mode).
    """
    if not _TOKEN:
        return {}
    return {"Authorization": f"Bearer {_TOKEN}"}
