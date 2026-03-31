"""Unit tests for core/hermes_integration.py.

Tests cover:
  - HERMES_TOOL_METADATA 상수 정의 검증.
  - HermesRuntime.on_init: Tool Registry 등록 + Platform Adapter 등록.
  - HermesRuntime.on_message: normalize_inbound 위임 (no-op 안전).
  - HermesRuntime.on_teardown: shutdown 훅 호출.
  - register_hermes_tools: 도구 등록 반환값 검증.
  - get_hermes_runtime / reset_hermes_runtime: 싱글턴 관리.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Module reload helper
# ---------------------------------------------------------------------------


def _reload_integration():
    """hermes_integration 모듈을 새로 로드하여 싱글턴을 초기화합니다."""
    for mod in ["core.hermes_integration", "core.tool_registry", "core.platform_adapter"]:
        sys.modules.pop(mod, None)
    os.environ["ENABLE_TOOL_REGISTRY"] = "true"
    os.environ["ENABLE_PLATFORM_ADAPTER"] = "true"
    import core.hermes_integration as hi
    hi.reset_hermes_runtime()
    return hi


# ---------------------------------------------------------------------------
# Fake Telegram Update for testing
# ---------------------------------------------------------------------------


@dataclass
class _FakeChat:
    id: int = 123


@dataclass
class _FakeUser:
    id: int = 456


@dataclass
class _FakeMessage:
    message_id: int = 1
    chat: _FakeChat = None
    from_user: _FakeUser = None
    text: str = "hello"

    def __post_init__(self):
        if self.chat is None:
            self.chat = _FakeChat()
        if self.from_user is None:
            self.from_user = _FakeUser()


@dataclass
class _FakeUpdate:
    message: _FakeMessage = None

    def __post_init__(self):
        if self.message is None:
            self.message = _FakeMessage()

    @property
    def effective_message(self):
        return self.message


# ---------------------------------------------------------------------------
# HERMES_TOOL_METADATA 상수 검증
# ---------------------------------------------------------------------------


class TestHermesToolMetadata:
    def setup_method(self):
        self.hi = _reload_integration()

    def test_metadata_keys_exist(self):
        assert "dispatch" in self.hi.HERMES_TOOL_METADATA
        assert "compress_context" in self.hi.HERMES_TOOL_METADATA
        assert "normalize_inbound" in self.hi.HERMES_TOOL_METADATA

    def test_each_entry_has_required_fields(self):
        for key, meta in self.hi.HERMES_TOOL_METADATA.items():
            assert "tool_name" in meta, f"{key}: tool_name 누락"
            assert "description" in meta, f"{key}: description 누락"
            assert "input_schema" in meta, f"{key}: input_schema 누락"
            assert isinstance(meta["input_schema"], dict), f"{key}: input_schema must be dict"

    def test_tool_names_are_strings(self):
        for key, meta in self.hi.HERMES_TOOL_METADATA.items():
            assert isinstance(meta["tool_name"], str)
            assert len(meta["tool_name"]) > 0


# ---------------------------------------------------------------------------
# register_hermes_tools 검증
# ---------------------------------------------------------------------------


class TestRegisterHermesTools:
    def setup_method(self):
        self.hi = _reload_integration()

    def test_register_returns_count(self):
        from core.tool_registry import get_registry, reset_registry
        reset_registry()
        reg = get_registry()
        count = self.hi.register_hermes_tools(reg)
        assert count == len(self.hi.HERMES_TOOL_METADATA)

    def test_tools_are_in_registry(self):
        from core.tool_registry import get_registry, reset_registry
        reset_registry()
        reg = get_registry()
        self.hi.register_hermes_tools(reg)
        all_tools = reg.list_all()
        registered_names = {t.name for t in all_tools}
        for meta in self.hi.HERMES_TOOL_METADATA.values():
            assert meta["tool_name"] in registered_names

    def test_tools_have_hermes_tag(self):
        from core.tool_registry import get_registry, reset_registry
        reset_registry()
        reg = get_registry()
        self.hi.register_hermes_tools(reg)
        hermes_tools = reg.get_tools_by_tag("hermes")
        assert len(hermes_tools) == len(self.hi.HERMES_TOOL_METADATA)

    def test_register_on_bad_registry_does_not_raise(self):
        """레지스트리가 망가져도 예외 전파 없이 0 반환."""
        class BrokenRegistry:
            def register(self, *a, **kw):
                raise RuntimeError("broken")

        count = self.hi.register_hermes_tools(BrokenRegistry())
        assert count == 0


# ---------------------------------------------------------------------------
# HermesRuntime 훅 검증
# ---------------------------------------------------------------------------


class TestHermesRuntimeHooks:
    def setup_method(self):
        self.hi = _reload_integration()
        from core.tool_registry import reset_registry
        reset_registry()

    def test_on_init_succeeds_without_bot_sender(self):
        runtime = self.hi.HermesRuntime()
        runtime.on_init(bot_sender=None)
        assert runtime.is_initialized is True

    def test_on_init_with_bot_sender(self):
        calls = []

        def mock_sender(**kwargs):
            calls.append(kwargs)

        runtime = self.hi.HermesRuntime()
        runtime.on_init(bot_sender=mock_sender)
        assert runtime.is_initialized is True

    def test_on_init_registers_tools(self):
        runtime = self.hi.HermesRuntime()
        runtime.on_init()
        tools = runtime.list_registered_tools()
        assert len(tools) > 0
        assert any("hermes" in name for name in tools)

    def test_on_message_before_init_returns_none(self):
        runtime = self.hi.HermesRuntime()
        # on_init 호출 없이 on_message 호출 — no-op
        result = runtime.on_message(_FakeUpdate())
        assert result is None

    def test_on_message_after_init_returns_inbound(self):
        runtime = self.hi.HermesRuntime()
        runtime.on_init()
        result = runtime.on_message(_FakeUpdate())
        # ENABLE_PLATFORM_ADAPTER=true이면 InboundMessage 반환
        assert result is not None
        assert result.platform == "telegram"
        assert result.chat_id == "123"

    def test_on_message_none_event_returns_none(self):
        runtime = self.hi.HermesRuntime()
        runtime.on_init()
        result = runtime.on_message(None)
        assert result is None

    def test_on_teardown_resets_state(self):
        runtime = self.hi.HermesRuntime()
        runtime.on_init()
        assert runtime.is_initialized is True
        runtime.on_teardown()
        assert runtime.is_initialized is False

    def test_on_teardown_before_init_is_noop(self):
        runtime = self.hi.HermesRuntime()
        # on_init 없이 teardown — 예외 전파 없어야 함
        runtime.on_teardown()

    def test_list_registered_tools_before_init_empty(self):
        runtime = self.hi.HermesRuntime()
        assert runtime.list_registered_tools() == []


# ---------------------------------------------------------------------------
# 싱글턴 관리
# ---------------------------------------------------------------------------


class TestHermesRuntimeSingleton:
    def setup_method(self):
        self.hi = _reload_integration()

    def test_get_hermes_runtime_returns_same_instance(self):
        r1 = self.hi.get_hermes_runtime()
        r2 = self.hi.get_hermes_runtime()
        assert r1 is r2

    def test_reset_hermes_runtime_creates_new(self):
        r1 = self.hi.get_hermes_runtime()
        self.hi.reset_hermes_runtime()
        r2 = self.hi.get_hermes_runtime()
        assert r1 is not r2

    def test_reset_hermes_runtime_not_initialized(self):
        self.hi.reset_hermes_runtime()
        runtime = self.hi.get_hermes_runtime()
        assert runtime.is_initialized is False
