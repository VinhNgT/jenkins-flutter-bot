"""Active build store for Telegram webhook and Web App build tracking."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ActiveBuild:
    """An active build tracked for callback correlation."""

    chat_id: int
    ref: str
    label: str  # friendly display label (e.g. "Stable Release")
    request_id: str
    triggered_at: float
    triggered_by: str  # user display name
    triggered_by_id: int = 0  # user Telegram ID
    notify: bool = True  # whether to send result notification to chat


class ActiveBuildStore:
    """Minimal store mapping request_id → active build.

    No states, no transitions, no message tracking.
    Just register when a build starts, consume when it ends.
    """

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._builds: dict[str, ActiveBuild] = {}
        self._clock = clock
        self._listeners: set[asyncio.Event] = set()

    def add_listener(self, event: asyncio.Event) -> None:
        """Register an asyncio.Event listener to be notified on store mutations."""
        self._listeners.add(event)

    def remove_listener(self, event: asyncio.Event) -> None:
        """Remove an asyncio.Event listener."""
        self._listeners.discard(event)

    def _notify_listeners(self) -> None:
        """Set all registered event listeners to trigger immediate wakeup."""
        for event in list(self._listeners):
            event.set()

    def register(
        self,
        request_id: str,
        chat_id: int,
        ref: str,
        label: str,
        triggered_by: str,
        triggered_by_id: int = 0,
        *,
        notify: bool = True,
    ) -> ActiveBuild:
        """Register a new active build."""
        build = ActiveBuild(
            chat_id=chat_id,
            ref=ref,
            label=label,
            request_id=request_id,
            triggered_at=self._clock(),
            triggered_by=triggered_by,
            triggered_by_id=triggered_by_id,
            notify=notify,
        )
        self._builds[request_id] = build
        self._notify_listeners()
        return build

    def get(self, request_id: str) -> ActiveBuild | None:
        """Retrieve an active build by its request ID without removing it."""
        return self._builds.get(request_id)

    def consume(self, request_id: str) -> ActiveBuild | None:
        """Consume and return an active build by its request ID."""
        build = self._builds.pop(request_id, None)
        if build is not None:
            self._notify_listeners()
        return build

    def find_by_branch(self, ref: str) -> ActiveBuild | None:
        """Find an active build by its branch reference."""
        for build in self._builds.values():
            if build.ref == ref:
                return build
        return None

    def list_active(self) -> list[ActiveBuild]:
        """List all currently active builds."""
        return list(self._builds.values())

