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
"""

from __future__ import annotations

import time
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

    TTL applies only to picker states (``picking``, ``awaiting_text``).
    Build states (``building``, ``confirming_cancel``) are long-lived and
    only removed explicitly via :meth:`remove` or :meth:`transition` to
    ``done``.
    """

    _PICKER_STATES = frozenset({"picking", "awaiting_text"})

    def __init__(self, picker_ttl: int = 300) -> None:
        self._messages: dict[tuple[int, int], TrackedMessage] = {}
        self._picker_ttl = picker_ttl

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
            data=data or {},
        )
        self._messages[(chat_id, message_id)] = msg
        return msg

    # -- Queries --

    def get(self, chat_id: int, message_id: int) -> TrackedMessage | None:
        """Get a tracked message, or None if expired/missing.

        Picker-state messages are subject to TTL expiry.  Build-state
        messages are never expired by TTL — they persist until explicitly
        removed (via webhook callback or cancellation).
        """
        key = (chat_id, message_id)
        msg = self._messages.get(key)
        if msg is None:
            return None
        if (
            msg.state in self._PICKER_STATES
            and time.time() - msg.created_at > self._picker_ttl
        ):
            del self._messages[key]
            return None
        return msg

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
        now = time.time()
        for key, msg in list(self._messages.items()):
            if (
                msg.state in self._PICKER_STATES
                and now - msg.created_at > self._picker_ttl
            ):
                del self._messages[key]
                continue
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
        now = time.time()
        for msg_key, msg in list(self._messages.items()):
            if (
                msg.state in self._PICKER_STATES
                and now - msg.created_at > self._picker_ttl
            ):
                del self._messages[msg_key]
                continue
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
        now = time.time()
        result: list[TrackedMessage] = []
        for key, msg in list(self._messages.items()):
            if (
                msg.state in self._PICKER_STATES
                and now - msg.created_at > self._picker_ttl
            ):
                del self._messages[key]
                continue
            if msg.state == state:
                result.append(msg)
        return result
