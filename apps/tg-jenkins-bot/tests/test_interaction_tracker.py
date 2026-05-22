"""Tests for InteractionTracker — state machine, race conditions, queries."""

from tg_jenkins_bot.bot.tracker import InteractionTracker, TrackedMessage


# ---------------------------------------------------------------------------
# Registration & basic queries
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_get(self):
        tracker = InteractionTracker()
        msg = tracker.register(100, 1, 42, "picking")
        assert isinstance(msg, TrackedMessage)
        got = tracker.get(100, 1)
        assert got is msg
        assert got.state == "picking"

    def test_get_missing_returns_none(self):
        tracker = InteractionTracker()
        assert tracker.get(100, 999) is None

    def test_register_with_data(self):
        tracker = InteractionTracker()
        msg = tracker.register(100, 1, 42, "picking", data={"user_name": "Alice"})
        assert msg.data["user_name"] == "Alice"

    def test_register_overwrites_existing(self):
        """Re-registering same (chat_id, message_id) replaces the entry."""
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "picking")
        tracker.register(100, 1, 42, "building", data={"ref": "main"})
        assert tracker.get(100, 1).state == "building"


# ---------------------------------------------------------------------------
# State transitions — the core race-condition prevention mechanism
# ---------------------------------------------------------------------------


class TestTransitions:
    def test_transition_succeeds(self):
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "picking")
        result = tracker.transition(100, 1, "picking", "consumed")
        assert result is not None
        assert result.state == "consumed"

    def test_transition_wrong_state_returns_none(self):
        """Race: expected 'picking' but was already 'consumed'."""
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "consumed")
        result = tracker.transition(100, 1, "picking", "building")
        assert result is None

    def test_transition_missing_message_returns_none(self):
        tracker = InteractionTracker()
        result = tracker.transition(100, 999, "picking", "consumed")
        assert result is None

    def test_double_transition_only_first_wins(self):
        """Two callers race on same message — only one gets it."""
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "picking")

        winner = tracker.transition(100, 1, "picking", "consumed")
        loser = tracker.transition(100, 1, "picking", "consumed")

        assert winner is not None
        assert loser is None

    def test_transition_with_data_updates(self):
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "building", data={"ref": "main"})
        result = tracker.transition(100, 1, "building", "done", {"result": "success"})
        assert result.data["ref"] == "main"
        assert result.data["result"] == "success"

    def test_chained_transitions(self):
        """building → confirming_cancel → done"""
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "building")

        result = tracker.transition(100, 1, "building", "confirming_cancel")
        assert result is not None
        result = tracker.transition(100, 1, "confirming_cancel", "done")
        assert result is not None
        assert tracker.get(100, 1).state == "done"

    def test_transition_back(self):
        """confirming_cancel → building (user clicked 'Go back')."""
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "confirming_cancel")
        result = tracker.transition(100, 1, "confirming_cancel", "building")
        assert result is not None
        assert result.state == "building"


# ---------------------------------------------------------------------------
# Query methods
# ---------------------------------------------------------------------------


class TestQueries:
    def test_find_by_state_returns_first_match(self):
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "picking")
        tracker.register(100, 2, 42, "building")
        result = tracker.find_by_state(100, "picking")
        assert result is not None
        assert result.message_id == 1

    def test_find_by_state_wrong_chat(self):
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "picking")
        result = tracker.find_by_state(200, "picking")
        assert result is None

    def test_find_by_state_wrong_state(self):
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "building")
        result = tracker.find_by_state(100, "picking")
        assert result is None

    def test_find_by_data_cross_chat(self):
        """Finds by request_id across all chats."""
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "building", data={"request_id": "abc123"})
        tracker.register(200, 1, 42, "building", data={"request_id": "def456"})
        result = tracker.find_by_data("request_id", "abc123")
        assert result is not None
        assert result.chat_id == 100

    def test_find_by_data_not_found(self):
        tracker = InteractionTracker()
        assert tracker.find_by_data("request_id", "nonexistent") is None

    def test_list_by_state(self):
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "building")
        tracker.register(200, 2, 43, "building")
        tracker.register(100, 3, 42, "picking")
        result = tracker.list_by_state("building")
        assert len(result) == 2

    def test_list_by_state_empty(self):
        tracker = InteractionTracker()
        assert tracker.list_by_state("building") == []


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------


class TestRemoval:
    def test_remove_returns_and_deletes(self):
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "picking")
        removed = tracker.remove(100, 1)
        assert removed is not None
        assert removed.state == "picking"
        assert tracker.get(100, 1) is None

    def test_remove_missing_returns_none(self):
        tracker = InteractionTracker()
        assert tracker.remove(100, 999) is None

    def test_remove_idempotent(self):
        tracker = InteractionTracker()
        tracker.register(100, 1, 42, "picking")
        tracker.remove(100, 1)
        assert tracker.remove(100, 1) is None


# ---------------------------------------------------------------------------
# Clock injection
# ---------------------------------------------------------------------------


class TestClock:
    def test_clock_used_for_created_at(self):
        tracker = InteractionTracker(clock=lambda: 999.0)
        msg = tracker.register(100, 1, 42, "picking")
        assert msg.created_at == 999.0
