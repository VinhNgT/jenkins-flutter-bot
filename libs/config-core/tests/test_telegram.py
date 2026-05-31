"""Tests for Telegram initData HMAC-SHA256 verification."""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import time
import urllib.parse

import pytest
import time_machine

from config_core.telegram import verify_init_data

# Fixed test token — never used in production
_TEST_TOKEN = "1234567890:ABCdefGhIjKlMnOpQrStUvWxYz"

# Fixed timestamp: 2025-06-01 12:00:00 UTC
_AUTH_DATE = 1748779200


def _build_init_data(
    bot_token: str = _TEST_TOKEN,
    user_id: int = 99999,
    auth_date: int = _AUTH_DATE,
    extra_params: dict[str, str] | None = None,
) -> str:
    """Build a correctly-signed Telegram initData string.

    Mirrors the signature algorithm from Telegram's documentation:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    user_obj = json.dumps(
        {"id": user_id, "first_name": "Test", "last_name": "User"},
        separators=(",", ":"),
    )
    params: dict[str, str] = {
        "user": user_obj,
        "auth_date": str(auth_date),
    }
    if extra_params:
        params.update(extra_params)

    # Build data check string (sorted, newline-separated)
    sorted_params = sorted(params.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)

    # Derive HMAC secret: HMAC-SHA256(key="WebAppData", msg=bot_token)
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()

    # Compute hash
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    params["hash"] = computed_hash
    return urllib.parse.urlencode(params)


class TestValidSignature:
    """Happy path — correctly signed initData."""

    @time_machine.travel("2025-06-01 12:00:00", tick=False)
    def test_valid_signature_returns_parsed_user(self) -> None:
        init_data = _build_init_data()
        result = verify_init_data(init_data, _TEST_TOKEN)

        assert result["user"]["id"] == 99999
        assert result["user"]["first_name"] == "Test"
        assert result["auth_date"] == _AUTH_DATE

    @time_machine.travel("2025-06-01 12:00:00", tick=False)
    def test_preserves_extra_params(self) -> None:
        init_data = _build_init_data(extra_params={"query_id": "abc123"})
        result = verify_init_data(init_data, _TEST_TOKEN)

        assert result["query_id"] == "abc123"


class TestSignatureValidation:
    """Tampered or malformed signatures."""

    @time_machine.travel("2025-06-01 12:00:00", tick=False)
    def test_tampered_hash_raises(self) -> None:
        init_data = _build_init_data()
        # Replace the hash with a fake one
        tampered = init_data.replace(
            urllib.parse.urlencode({"hash": ""})[len("hash="):],
            "",
        )
        # More reliable: rebuild with wrong hash
        params = dict(urllib.parse.parse_qsl(init_data))
        params["hash"] = "a" * 64
        tampered = urllib.parse.urlencode(params)

        with pytest.raises(ValueError, match="Invalid hash"):
            verify_init_data(tampered, _TEST_TOKEN)

    @time_machine.travel("2025-06-01 12:00:00", tick=False)
    def test_tampered_user_field_raises(self) -> None:
        init_data = _build_init_data(user_id=99999)
        # Parse, modify user, re-encode (keeping original hash)
        params = dict(urllib.parse.parse_qsl(init_data))
        user = json.loads(params["user"])
        user["id"] = 11111  # Tamper the user ID
        params["user"] = json.dumps(user, separators=(",", ":"))
        tampered = urllib.parse.urlencode(params)

        with pytest.raises(ValueError, match="Invalid hash"):
            verify_init_data(tampered, _TEST_TOKEN)

    @time_machine.travel("2025-06-01 12:00:00", tick=False)
    def test_wrong_bot_token_raises(self) -> None:
        init_data = _build_init_data()

        with pytest.raises(ValueError, match="Invalid hash"):
            verify_init_data(init_data, "9999999999:WrongToken")

    def test_missing_hash_raises(self) -> None:
        params = urllib.parse.urlencode({
            "user": json.dumps({"id": 1}),
            "auth_date": str(_AUTH_DATE),
        })
        with pytest.raises(ValueError, match="Missing hash"):
            verify_init_data(params, _TEST_TOKEN)

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing hash"):
            verify_init_data("", _TEST_TOKEN)


class TestReplayProtection:
    """auth_date-based TTL enforcement (1 hour window)."""

    def test_missing_auth_date_raises(self) -> None:
        """initData without auth_date is rejected."""
        params = {
            "user": json.dumps({"id": 99999}),
        }
        sorted_params = sorted(params.items())
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
        secret_key = hmac.new(
            b"WebAppData", _TEST_TOKEN.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        params["hash"] = computed_hash
        init_data = urllib.parse.urlencode(params)

        with pytest.raises(ValueError, match="Missing auth_date"):
            verify_init_data(init_data, _TEST_TOKEN)

    def test_expired_init_data_raises(self) -> None:
        """initData signed >1 hour ago is rejected."""
        old_auth_date = int(time.time()) - 3601
        init_data = _build_init_data(auth_date=old_auth_date)

        with pytest.raises(ValueError, match="expired"):
            verify_init_data(init_data, _TEST_TOKEN)

    def test_boundary_exactly_one_hour_accepted(self) -> None:
        """initData signed exactly 1 hour ago is still valid."""
        with time_machine.travel("2025-06-01 13:00:00", tick=False):
            init_data = _build_init_data(auth_date=_AUTH_DATE)
            # _AUTH_DATE is 12:00:00, current is 13:00:00 = exactly 3600s
            result = verify_init_data(init_data, _TEST_TOKEN)
            assert result["user"]["id"] == 99999

    def test_fresh_init_data_accepted(self) -> None:
        """initData signed 30 seconds ago is valid."""
        recent = int(time.time()) - 30
        init_data = _build_init_data(auth_date=recent)
        result = verify_init_data(init_data, _TEST_TOKEN)
        assert result["user"]["id"] == 99999


class TestConstantTimeComparison:
    """Verify the implementation uses constant-time comparison."""

    def test_uses_hmac_compare_digest(self) -> None:
        """The source code must use hmac.compare_digest, not == operator."""
        source = inspect.getsource(verify_init_data)
        assert "compare_digest" in source, (
            "verify_init_data must use hmac.compare_digest for "
            "constant-time hash comparison to prevent timing attacks"
        )
