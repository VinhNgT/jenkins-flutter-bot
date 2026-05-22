"""Tests for ConfigDocument — nested dict get/set/merge operations."""

from config_core.schema import ConfigDocument


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


class TestGet:
    def test_simple_key(self):
        doc = ConfigDocument({"name": "bot"})
        assert doc.get("name") == "bot"

    def test_dotted_key(self):
        doc = ConfigDocument({"telegram": {"bot_token": "abc"}})
        assert doc.get("telegram.bot_token") == "abc"

    def test_missing_key_returns_none(self):
        doc = ConfigDocument({"a": 1})
        assert doc.get("b") is None

    def test_missing_nested_key_returns_none(self):
        doc = ConfigDocument({"a": {"b": 1}})
        assert doc.get("a.c") is None

    def test_deeply_nested(self):
        doc = ConfigDocument({"a": {"b": {"c": {"d": 42}}}})
        assert doc.get("a.b.c.d") == 42

    def test_non_dict_intermediate_returns_none(self):
        """When an intermediate key is a string (not a dict), return None."""
        doc = ConfigDocument({"a": "just a string"})
        assert doc.get("a.b") is None

    def test_none_data(self):
        doc = ConfigDocument(None)
        assert doc.get("anything") is None

    def test_empty_data(self):
        doc = ConfigDocument({})
        assert doc.get("key") is None

    def test_value_is_none(self):
        """get() should return None when the actual value is None."""
        doc = ConfigDocument({"key": None})
        assert doc.get("key") is None

    def test_value_is_falsy(self):
        """get() should return falsy values (0, False, '') without confusing them with missing."""
        doc = ConfigDocument({"zero": 0, "false": False, "empty": ""})
        assert doc.get("zero") == 0
        assert doc.get("false") is False
        assert doc.get("empty") == ""


# ---------------------------------------------------------------------------
# Constructor reference identity
# ---------------------------------------------------------------------------


class TestInit:
    def test_empty_dict_preserves_reference(self):
        """ConfigDocument({}) must use the SAME dict object, not create a new one.

        Regression: `data or {}` treated {} as falsy and created a new dict,
        severing the reference between the caller's dict and doc.data.
        This broke _parse_env_content where modifications via doc.set()
        were invisible to the caller.
        """
        d = {}
        doc = ConfigDocument(d)
        assert doc.data is d

    def test_none_creates_new_dict(self):
        doc = ConfigDocument(None)
        assert doc.data == {}

    def test_no_args_creates_new_dict(self):
        doc = ConfigDocument()
        assert doc.data == {}

    def test_non_empty_dict_preserves_reference(self):
        d = {"key": "val"}
        doc = ConfigDocument(d)
        assert doc.data is d

    def test_set_on_empty_dict_visible_to_caller(self):
        """Mutations via set() on an initially-empty dict are visible to the caller."""
        d = {}
        doc = ConfigDocument(d)
        doc.set("a.b", 1)
        assert d == {"a": {"b": 1}}


# ---------------------------------------------------------------------------
# set()
# ---------------------------------------------------------------------------


class TestSet:
    def test_simple_key(self):
        doc = ConfigDocument({})
        doc.set("name", "bot")
        assert doc.data == {"name": "bot"}

    def test_creates_intermediate_dicts(self):
        doc = ConfigDocument({})
        doc.set("a.b.c", 1)
        assert doc.data == {"a": {"b": {"c": 1}}}

    def test_overwrites_existing(self):
        doc = ConfigDocument({"a": {"b": "old"}})
        doc.set("a.b", "new")
        assert doc.data["a"]["b"] == "new"

    def test_overwrites_non_dict_intermediate(self):
        """set('a.b', 1) where a was a string → creates dict."""
        doc = ConfigDocument({"a": "was a string"})
        doc.set("a.b", 1)
        assert doc.data == {"a": {"b": 1}}

    def test_preserves_siblings(self):
        doc = ConfigDocument({"a": {"b": 1, "c": 2}})
        doc.set("a.b", 99)
        assert doc.data == {"a": {"b": 99, "c": 2}}


# ---------------------------------------------------------------------------
# merge()
# ---------------------------------------------------------------------------


class TestMerge:
    def test_disjoint_dicts(self):
        doc = ConfigDocument({"a": 1})
        doc.merge({"b": 2})
        assert doc.data == {"a": 1, "b": 2}

    def test_deep_preserves_siblings(self):
        """Updating a.b doesn't remove a.c."""
        doc = ConfigDocument({"a": {"b": 1, "c": 2}})
        doc.merge({"a": {"b": 99}})
        assert doc.data == {"a": {"b": 99, "c": 2}}

    def test_replaces_lists(self):
        """Lists are overwritten, not appended."""
        doc = ConfigDocument({"items": [1, 2]})
        doc.merge({"items": [3]})
        assert doc.data == {"items": [3]}

    def test_replaces_primitives(self):
        doc = ConfigDocument({"count": 1})
        doc.merge({"count": 2})
        assert doc.data == {"count": 2}

    def test_nested_merge_three_levels(self):
        doc = ConfigDocument({"a": {"b": {"c": 1, "d": 2}}})
        doc.merge({"a": {"b": {"c": 99}}})
        assert doc.data == {"a": {"b": {"c": 99, "d": 2}}}

    def test_merge_new_nested_key(self):
        doc = ConfigDocument({"a": {"b": 1}})
        doc.merge({"a": {"c": 2}})
        assert doc.data == {"a": {"b": 1, "c": 2}}

    def test_merge_empty_update(self):
        doc = ConfigDocument({"a": 1})
        doc.merge({})
        assert doc.data == {"a": 1}

    def test_merge_into_empty(self):
        doc = ConfigDocument({})
        doc.merge({"a": {"b": 1}})
        assert doc.data == {"a": {"b": 1}}
