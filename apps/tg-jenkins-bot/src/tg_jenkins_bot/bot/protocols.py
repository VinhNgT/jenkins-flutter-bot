"""Protocols for testable Telegram bot interfaces.

Defines :class:`BotLike`, the minimal bot interface consumed by
:class:`BotContext`.  ``telegram.Bot`` satisfies this via structural
subtyping; ``AsyncMock`` satisfies it at runtime.  Tests never need
to import ``telegram.Bot`` to construct a working ``BotContext``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BotLike(Protocol):
    """Minimal bot interface used by BotContext for messaging.

    Only the two Telegram Bot methods that BotContext actually calls
    are declared here.  Any object implementing these two methods
    (including ``AsyncMock``) is a valid substitute.
    """

    async def edit_message_text(
        self,
        text: str,
        chat_id: int | None = ...,
        message_id: int | None = ...,
        *,
        parse_mode: str | None = ...,
        reply_markup: Any = ...,
    ) -> Any: ...

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None = ...,
        reply_markup: Any = ...,
    ) -> Any: ...
