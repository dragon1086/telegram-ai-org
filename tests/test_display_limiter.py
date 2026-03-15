"""DisplayLimiter 단위 테스트."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.display_limiter import DisplayLimiter, MessagePriority


class FakeMessage:
    def __init__(self):
        self.reply_text = AsyncMock()
        self.edit_text = AsyncMock()


@pytest.mark.asyncio
async def test_send_reply_immediate():
    limiter = DisplayLimiter(debounce_sec=5.0)
    msg = FakeMessage()
    await limiter.send_reply(msg, "hello", priority=MessagePriority.IMMEDIATE)
    msg.reply_text.assert_awaited_once_with("hello")


@pytest.mark.asyncio
async def test_send_to_chat_always_immediate():
    limiter = DisplayLimiter(debounce_sec=5.0)
    bot = AsyncMock()
    await limiter.send_to_chat(bot, chat_id=123, text="collab msg")
    bot.send_message.assert_awaited_once_with(chat_id=123, text="collab msg")


@pytest.mark.asyncio
async def test_send_to_chat_with_reply_to():
    limiter = DisplayLimiter(debounce_sec=5.0)
    bot = AsyncMock()
    await limiter.send_to_chat(bot, chat_id=123, text="collab msg", reply_to_message_id=9)
    bot.send_message.assert_awaited_once_with(
        chat_id=123,
        text="collab msg",
        reply_to_message_id=9,
    )


@pytest.mark.asyncio
async def test_send_to_chat_retries_without_reply_on_missing_target():
    limiter = DisplayLimiter(debounce_sec=5.0)
    bot = AsyncMock()
    bot.send_message.side_effect = [Exception("Message to be replied not found"), object()]

    await limiter.send_to_chat(bot, chat_id=123, text="collab msg", reply_to_message_id=9)

    assert bot.send_message.await_count == 2
    assert bot.send_message.await_args_list[1].kwargs == {"chat_id": 123, "text": "collab msg"}


@pytest.mark.asyncio
async def test_send_reply_retries_without_reply_on_missing_target():
    limiter = DisplayLimiter(debounce_sec=5.0)
    msg = FakeMessage()
    msg.reply_text.side_effect = [Exception("Message to be replied not found"), object()]

    await limiter.send_reply(msg, "hello", reply_to_message_id=9)

    assert msg.reply_text.await_count == 2
    assert msg.reply_text.await_args_list[1].args == ("hello",)


@pytest.mark.asyncio
async def test_edit_progress_debounce():
    limiter = DisplayLimiter(debounce_sec=0.1)
    await limiter.start()
    try:
        progress_msg = FakeMessage()
        await limiter.edit_progress(progress_msg, "update 1", agent_id="org1")
        await limiter.edit_progress(progress_msg, "update 2", agent_id="org1")
        await limiter.edit_progress(progress_msg, "update 3", agent_id="org1")
        await asyncio.sleep(0.25)
        calls = progress_msg.edit_text.call_args_list
        assert len(calls) >= 1
        assert calls[-1][0][0] == "update 3"
    finally:
        await limiter.stop()


@pytest.mark.asyncio
async def test_edit_progress_different_agents_independent():
    limiter = DisplayLimiter(debounce_sec=0.1)
    await limiter.start()
    try:
        msg1 = FakeMessage()
        msg2 = FakeMessage()
        await limiter.edit_progress(msg1, "agent1 update", agent_id="agent1")
        await limiter.edit_progress(msg2, "agent2 update", agent_id="agent2")
        await asyncio.sleep(0.25)
        msg1.edit_text.assert_awaited()
        msg2.edit_text.assert_awaited()
    finally:
        await limiter.stop()


@pytest.mark.asyncio
async def test_disabled_sends_immediately():
    limiter = DisplayLimiter(debounce_sec=5.0, enabled=False)
    progress_msg = FakeMessage()
    await limiter.edit_progress(progress_msg, "direct", agent_id="org1")
    progress_msg.edit_text.assert_awaited_once_with("direct")


@pytest.mark.asyncio
async def test_flush_error_does_not_crash():
    limiter = DisplayLimiter(debounce_sec=0.1)
    await limiter.start()
    try:
        failing_msg = FakeMessage()
        failing_msg.edit_text.side_effect = Exception("Telegram error")
        ok_msg = FakeMessage()
        await limiter.edit_progress(failing_msg, "fail", agent_id="fail_agent")
        await limiter.edit_progress(ok_msg, "ok", agent_id="ok_agent")
        await asyncio.sleep(0.25)
        ok_msg.edit_text.assert_awaited()
    finally:
        await limiter.stop()


@pytest.mark.asyncio
async def test_stop_flushes_pending():
    limiter = DisplayLimiter(debounce_sec=10.0)
    await limiter.start()
    msg = FakeMessage()
    await limiter.edit_progress(msg, "pending msg", agent_id="org1")
    await limiter.stop()
    msg.edit_text.assert_awaited_once_with("pending msg")
