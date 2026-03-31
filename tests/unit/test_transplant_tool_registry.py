"""Unit tests for core/tool_registry.py (P0-1: Tool Registry Pattern).

Tests cover:
  - Feature flag off: all operations are safe no-ops.
  - Feature flag on: register, get, dispatch, tag lookup, unregister.
  - Edge cases: duplicate names, None handler, unknown tool, empty tags.
"""
from __future__ import annotations

import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_registry(enabled: bool):
    """Reload the tool_registry module with the given flag value."""
    os.environ["ENABLE_TOOL_REGISTRY"] = "true" if enabled else "false"
    # Remove cached module so flag is re-evaluated
    mod_name = "core.tool_registry"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    from core import tool_registry as tr
    tr.reset_registry()
    return tr


# ---------------------------------------------------------------------------
# Flag=off tests
# ---------------------------------------------------------------------------


class TestToolRegistryDisabled:
    def setup_method(self):
        self.tr = _reload_registry(enabled=False)

    def test_register_is_noop(self):
        self.tr.get_registry().register("my_tool", "desc", handler=lambda: "hi")
        assert len(self.tr.get_registry()) == 0

    def test_get_returns_none(self):
        assert self.tr.get_registry().get("anything") is None

    def test_dispatch_returns_none(self):
        result = self.tr.get_registry().dispatch("anything")
        assert result is None

    def test_get_tools_by_tag_empty(self):
        assert self.tr.get_registry().get_tools_by_tag("x") == []

    def test_list_all_empty(self):
        assert self.tr.get_registry().list_all() == []

    def test_all_tags_empty(self):
        assert self.tr.get_registry().all_tags() == set()

    def test_len_zero(self):
        assert len(self.tr.get_registry()) == 0


# ---------------------------------------------------------------------------
# Flag=on tests
# ---------------------------------------------------------------------------


class TestToolRegistryEnabled:
    def setup_method(self):
        self.tr = _reload_registry(enabled=True)

    def test_register_and_get(self):
        reg = self.tr.get_registry()
        reg.register("hello", "says hello", handler=lambda: "hello")
        entry = reg.get("hello")
        assert entry is not None
        assert entry.name == "hello"

    def test_duplicate_registration_overwrites(self):
        reg = self.tr.get_registry()
        reg.register("dup", "first", handler=lambda: 1)
        reg.register("dup", "second", handler=lambda: 2)
        assert reg.get("dup").description == "second"
        assert len(reg) == 1

    def test_dispatch_calls_handler(self):
        reg = self.tr.get_registry()
        reg.register("add", "add two numbers", handler=lambda a, b: a + b)
        result = reg.dispatch("add", a=3, b=4)
        assert result == 7

    def test_dispatch_unknown_returns_none(self, caplog):
        reg = self.tr.get_registry()
        result = reg.dispatch("nonexistent")
        assert result is None

    def test_dispatch_none_handler(self, caplog):
        reg = self.tr.get_registry()
        reg.register("no_handler", "no handler", handler=None)
        result = reg.dispatch("no_handler")
        assert result is None

    def test_get_tools_by_tag(self):
        reg = self.tr.get_registry()
        reg.register("r1", "d1", tags={"file", "read"})
        reg.register("r2", "d2", tags={"file", "write"})
        reg.register("r3", "d3", tags={"network"})
        file_tools = reg.get_tools_by_tag("file")
        names = {e.name for e in file_tools}
        assert "r1" in names
        assert "r2" in names
        assert "r3" not in names

    def test_get_tools_by_multiple_tags(self):
        reg = self.tr.get_registry()
        reg.register("t1", "d1", tags={"file", "read", "async"})
        reg.register("t2", "d2", tags={"file", "read"})
        result = reg.get_tools_by_tag("file", "async")
        assert len(result) == 1
        assert result[0].name == "t1"

    def test_get_tools_no_tags_returns_all(self):
        reg = self.tr.get_registry()
        reg.register("a", "d")
        reg.register("b", "d")
        result = reg.get_tools_by_tag()
        assert len(result) == 2

    def test_unregister(self):
        reg = self.tr.get_registry()
        reg.register("bye", "desc")
        assert reg.get("bye") is not None
        removed = reg.unregister("bye")
        assert removed is True
        assert reg.get("bye") is None

    def test_unregister_missing_returns_false(self):
        reg = self.tr.get_registry()
        assert reg.unregister("ghost") is False

    def test_all_tags(self):
        reg = self.tr.get_registry()
        reg.register("x", "d", tags={"alpha", "beta"})
        reg.register("y", "d", tags={"beta", "gamma"})
        tags = reg.all_tags()
        assert tags == {"alpha", "beta", "gamma"}

    def test_invalid_name_skipped(self):
        reg = self.tr.get_registry()
        reg.register("", "empty name")
        assert len(reg) == 0

    def test_disabled_tool_excluded_from_tag_search(self):
        reg = self.tr.get_registry()
        reg.register("active", "d", tags={"io"}, enabled=True)
        reg.register("inactive", "d", tags={"io"}, enabled=False)
        result = reg.get_tools_by_tag("io")
        names = {e.name for e in result}
        assert "active" in names
        assert "inactive" not in names

    def test_dispatch_raises_on_handler_exception(self):
        reg = self.tr.get_registry()

        def bad_handler():
            raise RuntimeError("boom")

        reg.register("bad", "raises", handler=bad_handler)
        with pytest.raises(RuntimeError, match="boom"):
            reg.dispatch("bad")
