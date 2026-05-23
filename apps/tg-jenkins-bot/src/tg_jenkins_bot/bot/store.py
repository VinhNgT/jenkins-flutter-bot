"""Active build store for Telegram webhook and Web App build tracking."""

from __future__ import annotations

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


class ActiveBuildStore:
    """Minimal store mapping request_id → active build.

    No states, no transitions, no message tracking.
    Just register when a build starts, consume when it ends.
    """

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._builds: dict[str, ActiveBuild] = {}
        self._clock = clock

    def register(
        self,
        request_id: str,
        chat_id: int,
        ref: str,
        label: str,
        triggered_by: str,
    ) -> ActiveBuild:
        """Register a new active build."""
        build = ActiveBuild(
            chat_id=chat_id,
            ref=ref,
            label=label,
            request_id=request_id,
            triggered_at=self._clock(),
            triggered_by=triggered_by,
        )
        self._builds[request_id] = build
        return build

    def consume(self, request_id: str) -> ActiveBuild | None:
        """Consume and return an active build by its request ID."""
        return self._builds.pop(request_id, None)

    def find_by_branch(self, ref: str) -> ActiveBuild | None:
        """Find an active build by its branch reference."""
        for build in self._builds.values():
            if build.ref == ref:
                return build
        return None

    def list_active(self) -> list[ActiveBuild]:
        """List all currently active builds."""
        return list(self._builds.values())
