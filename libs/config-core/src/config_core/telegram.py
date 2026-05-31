"""Telegram initData HMAC verification.

Validates the cryptographic signature on Telegram Mini App ``initData``
to prove the request originated from a legitimate Telegram client.
Used by both ``tg-jenkins-bot`` (user auth) and ``config-hub`` (admin auth).

Algorithm: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Usage::

    from config_core import verify_init_data

    data = verify_init_data(raw_init_data, bot_token)
    user_id = data["user"]["id"]
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Any

# initData is valid for 1 hour after auth_date. The HMAC proves authenticity
# but never expires — without this TTL, a captured initData (from browser
# history, DevTools, or SSE query params) could be replayed indefinitely.
_INIT_DATA_TTL = 3600


def verify_init_data(init_data: str, bot_token: str) -> dict[str, Any]:
    """Verify Telegram initData HMAC-SHA256 signature and return parsed data.

    Args:
        init_data: Raw URL-encoded initData string from the Telegram Mini App.
        bot_token: The bot token used to derive the HMAC secret key.

    Returns:
        Parsed initData dict with nested JSON structures decoded.

    Raises:
        ValueError: If the signature is invalid, the hash is missing,
            or the initData has expired.
    """
    params = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    params_dict = dict(params)

    if "hash" not in params_dict:
        raise ValueError("Missing hash parameter")

    received_hash = params_dict.pop("hash")

    # Sort key-value pairs alphabetically for the data check string
    sorted_params = sorted(params_dict.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)

    # Derive secret key: HMAC-SHA256(key="WebAppData", msg=bot_token)
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()

    # Compute HMAC-SHA256 of the data check string
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid hash signature")

    # Replay protection: reject initData if auth_date is missing or older than the TTL
    auth_date_str = params_dict.get("auth_date")
    if not auth_date_str:
        raise ValueError("Missing auth_date parameter")

    auth_date = int(auth_date_str)
    if time.time() - auth_date > _INIT_DATA_TTL:
        raise ValueError("initData expired (auth_date too old)")

    # Parse nested JSON structures (e.g. user, chat objects)
    result: dict[str, Any] = {}
    for k, v in params_dict.items():
        try:
            result[k] = json.loads(v)
        except json.JSONDecodeError:
            result[k] = v

    return result
