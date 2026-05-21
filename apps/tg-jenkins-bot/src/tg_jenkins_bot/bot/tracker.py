"""Message-scoped interaction tracker.

Every interactive Telegram message is registered here with an explicit
state.  The callback router validates state before dispatching, making
invalid transitions structurally impossible.

Replaces both ``BuildSession`` and ``PendingBuild`` from the old
architecture with a single ``TrackedMessage`` keyed by
``(chat_id, message_id)``.

States
------
- ``picking``           — branch picker shown, waiting for button tap
- ``awaiting_text``     — "Type a name" tapped, waiting for free text
- ``building``          — build triggered, waiting for result callback
- ``confirming_cancel`` — "Cancel" tapped, showing confirmation
- ``done``              — terminal state (success, failure, cancelled)

Expiry
------
The tracker is a **pure state store** — it does not enforce TTL or
silently evict entries.  Picker expiration is handled exclusively by
the active JobQueue timer (``BotContext.expire_picker``), which removes
the entry and edits the Telegram message when the TTL elapses.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrackedMessage:
    """State of a single interactive Telegram message."""

    chat_id: int
    message_id: int
    user_id: int
    state: str
    created_at: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)


class InteractionTracker:
    """Central registry for all interactive messages.

    Tracks every interactive Telegram message by ``(chat_id, message_id)``.
    Provides state queries, validated transitions, and chat-level locks.

    This is a pure state store — it does **not** enforce TTL or silently
    evict entries.  Picker expiration is handled by the active JobQueue
    timer (see ``BotContext.expire_picker``).  The ``_picker_ttl`` value
    is stored here as a configuration property, read by ``BotContext``
    for scheduling the timer and formatting the expiry message.
    """

    _PICKER_STATES = frozenset({"picking", "awaiting_text"})

    def __init__(
        self, picker_ttl: int = 60, *, clock: Callable[[], float] = time.time,
    ) -> None:
        self._messages: dict[tuple[int, int], TrackedMessage] = {}
        self._picker_ttl = picker_ttl
        self._clock = clock

    # -- Registration --

    def register(
        self,
        chat_id: int,
        message_id: int,
        user_id: int,
        state: str,
        data: dict[str, Any] | None = None,
    ) -> TrackedMessage:
        """Register a new interactive message."""
        msg = TrackedMessage(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            state=state,
            created_at=self._clock(),
            data=data or {},
        )
        self._messages[(chat_id, message_id)] = msg
        return msg

    # -- Queries --

    def get(self, chat_id: int, message_id: int) -> TrackedMessage | None:
        """Get a tracked message, or None if missing."""
        return self._messages.get((chat_id, message_id))

    def find_by_state(
        self,
        chat_id: int,
        state: str,
    ) -> TrackedMessage | None:
        """Find a tracked message in a given state for a chat.

        Used for chat-level locks (e.g., "is there an active picker?")
        and for finding the building message for a given branch.
        Returns the first match, or None.
        """
        for msg in self._messages.values():
            if msg.chat_id == chat_id and msg.state == state:
                return msg
        return None

    def find_by_data(
        self,
        key_name: str,
        value: Any,
    ) -> TrackedMessage | None:
        """Find a tracked message by a data field value (global).

        Used for webhook callbacks where we only have request_id and
        need to find the corresponding building message across all chats.
        """
        for msg in self._messages.values():
            if msg.data.get(key_name) == value:
                return msg
        return None

    # -- Transitions --

    def transition(
        self,
        chat_id: int,
        message_id: int,
        expected_state: str,
        new_state: str,
        data_updates: dict[str, Any] | None = None,
    ) -> TrackedMessage | None:
        """Atomically transition a message from expected_state to new_state.

        Returns the updated TrackedMessage if the transition succeeded,
        or None if the message wasn't in expected_state.  Only one
        caller wins the race — this is the core mechanism that prevents
        all double-tap race conditions.
        """
        msg = self.get(chat_id, message_id)
        if msg is None or msg.state != expected_state:
            return None
        msg.state = new_state
        if data_updates:
            msg.data.update(data_updates)
        return msg

    # -- Removal --

    def remove(self, chat_id: int, message_id: int) -> TrackedMessage | None:
        """Remove and return a tracked message."""
        return self._messages.pop((chat_id, message_id), None)

    # -- Bulk queries --

    def list_by_state(self, state: str) -> list[TrackedMessage]:
        """List all tracked messages in a given state (across all chats)."""
        return [msg for msg in self._messages.values() if msg.state == state]
