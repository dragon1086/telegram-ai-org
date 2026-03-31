"""Unit tests for core/platform_adapter.py (P0-3: Platform Adapter Abstraction).

Tests cover:
  - Feature flag off: all adapter operations are safe no-ops.
  - Feature flag on: TelegramPlatformAdapter normalise/send, registry.
  - Edge cases: None event, missing chat_id, no bot_sender.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_adapter(enabled: bool):
    os.environ["ENABLE_PLATFORM_ADAPTER"] = "true" if enabled else "false"
    mod_name = "core.platform_adapter"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    import core.platform_adapter as pa
    # Reset adapters registry
    pa._adapters.clear()
    return pa


# ---------------------------------------------------------------------------
# Minimal fake Update for testing
# ---------------------------------------------------------------------------


@dataclass
class _FakeChat:
    id: int


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMessage:
    message_id: int
    chat: _FakeChat
    from_user: _FakeUser
    text: str


@dataclass
class _FakeUpdate:
    message: _FakeMessage

    @property
    def effective_message(self):
        return self.message


def _make_update(
    chat_id: int = 123,
    user_id: int = 456,
    message_id: int = 1,
    text: str = "hello",
) -> _FakeUpdate:
    return _FakeUpdate(
        message=_FakeMessage(
            message_id=message_id,
            chat=_FakeChat(id=chat_id),
            from_user=_FakeUser(id=user_id),
            text=text,
        )
    )


# ---------------------------------------------------------------------------
# Flag=off tests
# ---------------------------------------------------------------------------


class TestPlatformAdapterDisabled:
    def setup_method(self):
        self.pa = _reload_adapter(enabled=False)

    def test_normalize_returns_none(self):
        adapter = self.pa.TelegramPlatformAdapter()
        result = adapter.normalize_inbound(_make_update())
        assert result is None

    def test_send_returns_false(self):
        adapter = self.pa.TelegramPlatformAdapter()
        msg = self.pa.OutboundMessage(chat_id="1", text="hi")
        assert adapter.send_message(msg) is False

    def test_get_adapter_returns_none(self):
        assert self.pa.get_adapter("telegram") is None

    def test_list_adapters_empty(self):
        assert self.pa.list_adapters() == []


# ---------------------------------------------------------------------------
# Flag=on tests
# ---------------------------------------------------------------------------


class TestPlatformAdapterEnabled:
    def setup_method(self):
        self.pa = _reload_adapter(enabled=True)

    def test_normalize_valid_update(self):
        adapter = self.pa.TelegramPlatformAdapter()
        update = _make_update(chat_id=999, user_id=111, message_id=7, text="test msg")
        msg = adapter.normalize_inbound(update)
        assert msg is not None
        assert msg.platform == "telegram"
        assert msg.chat_id == "999"
        assert msg.sender_id == "111"
        assert msg.message_id == "7"
        assert msg.text == "test msg"

    def test_normalize_none_returns_none(self):
        adapter = self.pa.TelegramPlatformAdapter()
        assert adapter.normalize_inbound(None) is None

    def test_normalize_event_without_chat(self):
        # Object with effective_message but chat.id missing
        class BadMessage:
            message_id = 1
            chat = None
            from_user = None
            text = "x"

        class BadUpdate:
            effective_message = BadMessage()

        adapter = self.pa.TelegramPlatformAdapter()
        result = adapter.normalize_inbound(BadUpdate())
        assert result is None

    def test_send_calls_bot_sender(self):
        calls = []

        def mock_sender(**kwargs):
            calls.append(kwargs)

        adapter = self.pa.TelegramPlatformAdapter(bot_sender=mock_sender)
        msg = self.pa.OutboundMessage(chat_id="42", text="greetings")
        result = adapter.send_message(msg)
        assert result is True
        assert len(calls) == 1
        assert calls[0]["chat_id"] == "42"
        assert calls[0]["text"] == "greetings"

    def test_send_no_bot_sender_returns_false(self):
        adapter = self.pa.TelegramPlatformAdapter(bot_sender=None)
        msg = self.pa.OutboundMessage(chat_id="1", text="hi")
        assert adapter.send_message(msg) is False

    def test_send_empty_chat_id_returns_false(self):
        adapter = self.pa.TelegramPlatformAdapter(bot_sender=lambda **kw: None)
        msg = self.pa.OutboundMessage(chat_id="", text="hi")
        assert adapter.send_message(msg) is False

    def test_send_empty_text_returns_false(self):
        adapter = self.pa.TelegramPlatformAdapter(bot_sender=lambda **kw: None)
        msg = self.pa.OutboundMessage(chat_id="1", text="")
        assert adapter.send_message(msg) is False

    def test_register_and_get_adapter(self):
        adapter = self.pa.TelegramPlatformAdapter()
        self.pa.register_adapter(adapter)
        result = self.pa.get_adapter("telegram")
        assert result is adapter

    def test_list_adapters(self):
        adapter = self.pa.TelegramPlatformAdapter()
        self.pa.register_adapter(adapter)
        names = self.pa.list_adapters()
        assert "telegram" in names

    def test_register_non_adapter_ignored(self):
        self.pa.register_adapter("not-an-adapter")  # type: ignore
        assert self.pa.list_adapters() == []

    def test_can_handle_valid_update(self):
        adapter = self.pa.TelegramPlatformAdapter()
        assert adapter.can_handle(_make_update()) is True

    def test_can_handle_none_returns_false(self):
        adapter = self.pa.TelegramPlatformAdapter()
        assert adapter.can_handle(None) is False

    def test_platform_name(self):
        adapter = self.pa.TelegramPlatformAdapter()
        assert adapter.platform_name == "telegram"
