"""Unit tests for BotSettings configuration normalization."""

from __future__ import annotations

from tg_bot.config import BotSettings


def test_webapp_url_normalization() -> None:
    # 1. Bare domain name
    config1 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids=[12345],
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="tendoo-tg-bot.vinhngt.dev",
    )
    assert config1.webapp_url == "https://tendoo-tg-bot.vinhngt.dev/webapp/"

    # 2. Domain with slash
    config2 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids=[12345],
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="tendoo-tg-bot.vinhngt.dev/",
    )
    assert config2.webapp_url == "https://tendoo-tg-bot.vinhngt.dev/webapp/"

    # 3. Domain with partial webapp path
    config3 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids=[12345],
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="tendoo-tg-bot.vinhngt.dev/webapp",
    )
    assert config3.webapp_url == "https://tendoo-tg-bot.vinhngt.dev/webapp/"

    # 4. Domain with full HTTPS and webapp path
    config4 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids=[12345],
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="https://tendoo-tg-bot.vinhngt.dev/webapp/",
    )
    assert config4.webapp_url == "https://tendoo-tg-bot.vinhngt.dev/webapp/"

    # 5. Localhost HTTP url
    config5 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids=[12345],
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="http://localhost:9090",
    )
    assert config5.webapp_url == "http://localhost:9090/webapp/"


def test_branches_parsing() -> None:
    # 1. Dictionary input
    config1 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids=[12345],
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="http://localhost:9090",
        branches={"Production": "main", "Staging": "develop"},
    )
    assert config1.branches == {"Production": "main", "Staging": "develop"}

    # 2. JSON string input (as sent by our new KeyValueEditor)
    config2 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids=[12345],
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="http://localhost:9090",
        branches='{"Production": "main", "Staging": "develop"}',
    )
    assert config2.branches == {"Production": "main", "Staging": "develop"}

    # 3. Comma-separated string input fallback
    config3 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids=[12345],
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="http://localhost:9090",
        branches="main, develop",
    )
    assert config3.branches == {"main": "main", "develop": "develop"}


def test_allowed_chat_ids_parsing() -> None:
    # 1. Raw list of integers
    config1 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids=[123, -456],
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="http://localhost:9090",
    )
    assert config1.allowed_chat_ids == [123, -456]

    # 2. Comma-separated string
    config2 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids="123, -456",
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="http://localhost:9090",
    )
    assert config2.allowed_chat_ids == [123, -456]

    # 3. JSON array string
    config3 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids="[123, -456]",
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="http://localhost:9090",
    )
    assert config3.allowed_chat_ids == [123, -456]

    # 4. Empty string
    config4 = BotSettings(
        telegram_bot_token="123456:test-token",
        allowed_chat_ids="",
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="http://localhost:9090",
    )
    assert config4.allowed_chat_ids == []

    # 5. Omitted (should default to [])
    config5 = BotSettings(
        telegram_bot_token="123456:test-token",
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="http://localhost:9090",
    )
    assert config5.allowed_chat_ids == []


