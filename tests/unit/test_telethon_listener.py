"""TelethonListenerHelper 단위 테스트.

실제 Telethon 연결 없이 mock 객체로 min_id 필터링 로직과
채팅방별 독립 관리(dict 구조)를 검증한다.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.telethon_listener import (
    CollectedMessage,
    TelethonListenerHelper,
    _resolve_chat_id,
)


# ---------------------------------------------------------------------------
# 테스트용 픽스처 & 헬퍼
# ---------------------------------------------------------------------------


def _make_fake_message(msg_id: int, text: str = "hello") -> MagicMock:
    """Telethon Message mock 생성."""
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    return msg


def _make_fake_event(msg_id: int, text: str = "hello") -> MagicMock:
    """Telethon Event mock 생성."""
    event = MagicMock()
    event.message = _make_fake_message(msg_id, text)
    return event


def _make_bot_sender(username: str = "test_bot") -> MagicMock:
    """봇 sender mock 생성."""
    sender = MagicMock()
    sender.bot = True
    sender.username = username
    return sender


def _make_human_sender() -> MagicMock:
    """일반 유저 sender mock 생성."""
    sender = MagicMock()
    sender.bot = False
    sender.username = "human_user"
    return sender


def _make_chat_entity(chat_id: int) -> MagicMock:
    """Telethon chat entity mock 생성."""
    entity = MagicMock()
    entity.id = chat_id
    return entity


def _make_client(latest_msg_id: int = 100) -> AsyncMock:
    """Telethon TelegramClient mock 생성."""
    client = AsyncMock()
    fake_msg = _make_fake_message(latest_msg_id)
    client.get_messages = AsyncMock(return_value=[fake_msg])
    return client


# ---------------------------------------------------------------------------
# _resolve_chat_id 테스트
# ---------------------------------------------------------------------------


class TestResolveChatId:
    def test_int_passthrough(self):
        assert _resolve_chat_id(-1001234567890) == -1001234567890

    def test_entity_with_id_attr(self):
        entity = _make_chat_entity(42)
        assert _resolve_chat_id(entity) == 42

    def test_string_int(self):
        assert _resolve_chat_id("12345") == 12345

    def test_invalid_raises(self):
        with pytest.raises(TypeError):
            _resolve_chat_id(object())


# ---------------------------------------------------------------------------
# record_min_id 테스트
# ---------------------------------------------------------------------------


class TestRecordMinId:
    @pytest.mark.asyncio
    async def test_records_latest_message_id(self):
        client = _make_client(latest_msg_id=500)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)

        result = await helper.record_min_id(entity)

        assert result == 500
        assert helper.get_min_id(entity) == 500

    @pytest.mark.asyncio
    async def test_empty_chat_returns_zero(self):
        client = AsyncMock()
        client.get_messages = AsyncMock(return_value=[])
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)

        result = await helper.record_min_id(entity)

        assert result == 0
        assert helper.get_min_id(entity) == 0

    @pytest.mark.asyncio
    async def test_overwrite_previous_min_id(self):
        client = _make_client(latest_msg_id=200)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)

        await helper.record_min_id(entity)
        assert helper.get_min_id(entity) == 200

        # 재호출 시 갱신
        client.get_messages = AsyncMock(return_value=[_make_fake_message(300)])
        await helper.record_min_id(entity)
        assert helper.get_min_id(entity) == 300

    @pytest.mark.asyncio
    async def test_per_chat_independence(self):
        """채팅방 A 의 min_id 가 채팅방 B 에 영향을 주지 않는다."""
        entity_a = _make_chat_entity(111)
        entity_b = _make_chat_entity(222)

        client = AsyncMock()
        client.get_messages = AsyncMock(side_effect=[
            [_make_fake_message(100)],  # entity_a 용
            [_make_fake_message(200)],  # entity_b 용
        ])
        helper = TelethonListenerHelper(client)

        await helper.record_min_id(entity_a)
        await helper.record_min_id(entity_b)

        assert helper.get_min_id(entity_a) == 100
        assert helper.get_min_id(entity_b) == 200

    def test_get_min_id_before_record_returns_zero(self):
        client = AsyncMock()
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(99)
        assert helper.get_min_id(entity) == 0


# ---------------------------------------------------------------------------
# make_handler — min_id 필터 테스트
# ---------------------------------------------------------------------------


class TestMakeHandlerMinIdFilter:
    @pytest.mark.asyncio
    async def test_skips_message_equal_to_min_id(self):
        """event.message.id == min_id 는 skip."""
        client = _make_client(latest_msg_id=100)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)
        await helper.record_min_id(entity)  # min_id = 100

        collected: list[CollectedMessage] = []
        stop_flag = [False]
        handler = helper.make_handler(entity, collected, stop_flag)

        event = _make_fake_event(msg_id=100, text="old msg")
        event.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler(event)

        assert collected == []

    @pytest.mark.asyncio
    async def test_skips_message_less_than_min_id(self):
        """event.message.id < min_id 는 skip."""
        client = _make_client(latest_msg_id=100)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)
        await helper.record_min_id(entity)

        collected: list[CollectedMessage] = []
        stop_flag = [False]
        handler = helper.make_handler(entity, collected, stop_flag)

        event = _make_fake_event(msg_id=50)
        event.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler(event)

        assert collected == []

    @pytest.mark.asyncio
    async def test_collects_message_greater_than_min_id(self):
        """event.message.id > min_id 는 수집한다."""
        client = _make_client(latest_msg_id=100)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)
        await helper.record_min_id(entity)

        collected: list[CollectedMessage] = []
        stop_flag = [False]
        handler = helper.make_handler(entity, collected, stop_flag)

        event = _make_fake_event(msg_id=101, text="new bot message")
        event.get_sender = AsyncMock(return_value=_make_bot_sender("mybot"))
        await handler(event)

        assert len(collected) == 1
        assert collected[0].bot == "mybot"
        assert collected[0].text == "new bot message"

    @pytest.mark.asyncio
    async def test_stop_flag_halts_collection(self):
        """stop_flag[0] = True 이면 수집하지 않는다."""
        client = _make_client(latest_msg_id=0)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)
        await helper.record_min_id(entity)

        collected: list[CollectedMessage] = []
        stop_flag = [True]  # 이미 중단됨
        handler = helper.make_handler(entity, collected, stop_flag)

        event = _make_fake_event(msg_id=999, text="should not collect")
        event.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler(event)

        assert collected == []

    @pytest.mark.asyncio
    async def test_bot_only_skips_human_messages(self):
        """bot_only=True(기본) 이면 일반 유저 메시지는 수집하지 않는다."""
        client = _make_client(latest_msg_id=0)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)
        await helper.record_min_id(entity)

        collected: list[CollectedMessage] = []
        stop_flag = [False]
        handler = helper.make_handler(entity, collected, stop_flag, bot_only=True)

        event = _make_fake_event(msg_id=10, text="human message")
        event.get_sender = AsyncMock(return_value=_make_human_sender())
        await handler(event)

        assert collected == []

    @pytest.mark.asyncio
    async def test_bot_only_false_collects_all(self):
        """bot_only=False 이면 봇/유저 구분 없이 수집한다."""
        client = _make_client(latest_msg_id=0)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)
        await helper.record_min_id(entity)

        collected: list[CollectedMessage] = []
        stop_flag = [False]
        handler = helper.make_handler(entity, collected, stop_flag, bot_only=False)

        event = _make_fake_event(msg_id=5, text="any message")
        event.get_sender = AsyncMock(return_value=_make_human_sender())
        await handler(event)

        assert len(collected) == 1

    @pytest.mark.asyncio
    async def test_empty_text_skips(self):
        """text 가 빈 문자열이면 수집하지 않는다."""
        client = _make_client(latest_msg_id=0)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)
        await helper.record_min_id(entity)

        collected: list[CollectedMessage] = []
        stop_flag = [False]
        handler = helper.make_handler(entity, collected, stop_flag)

        event = _make_fake_event(msg_id=10, text="")
        event.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler(event)

        assert collected == []


# ---------------------------------------------------------------------------
# make_handler — on_message 커스텀 콜백 테스트
# ---------------------------------------------------------------------------


class TestMakeHandlerCustomCallback:
    @pytest.mark.asyncio
    async def test_custom_on_message_called(self):
        """on_message 콜백이 올바르게 호출된다."""
        client = _make_client(latest_msg_id=0)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)
        await helper.record_min_id(entity)

        call_log: list[tuple] = []

        async def my_callback(event, collected):
            call_log.append((event.message.id, event.message.text))

        collected: list[CollectedMessage] = []
        stop_flag = [False]
        handler = helper.make_handler(
            entity, collected, stop_flag, on_message=my_callback
        )

        event = _make_fake_event(msg_id=5, text="custom")
        event.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler(event)

        assert len(call_log) == 1
        assert call_log[0] == (5, "custom")

    @pytest.mark.asyncio
    async def test_min_id_filter_applies_before_custom_callback(self):
        """on_message 지정 시에도 min_id 필터는 동작해야 한다."""
        client = _make_client(latest_msg_id=100)
        helper = TelethonListenerHelper(client)
        entity = _make_chat_entity(1)
        await helper.record_min_id(entity)  # min_id = 100

        call_log: list[int] = []

        async def my_callback(event, collected):
            call_log.append(event.message.id)

        collected: list[CollectedMessage] = []
        stop_flag = [False]
        handler = helper.make_handler(
            entity, collected, stop_flag, on_message=my_callback
        )

        # min_id 이하 → callback 호출 안 됨
        old_event = _make_fake_event(msg_id=99)
        old_event.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler(old_event)

        # min_id 초과 → callback 호출됨
        new_event = _make_fake_event(msg_id=101)
        new_event.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler(new_event)

        assert call_log == [101]


# ---------------------------------------------------------------------------
# 채팅방 간 cross-contamination 방지 통합 테스트
# ---------------------------------------------------------------------------


class TestCrossChatIsolation:
    @pytest.mark.asyncio
    async def test_two_chats_independent_min_ids(self):
        """채팅방 A 핸들러는 채팅방 B 의 min_id 에 영향받지 않는다."""
        entity_a = _make_chat_entity(100)
        entity_b = _make_chat_entity(200)

        client = AsyncMock()
        client.get_messages = AsyncMock(side_effect=[
            [_make_fake_message(500)],   # entity_a: min_id = 500
            [_make_fake_message(1000)],  # entity_b: min_id = 1000
        ])
        helper = TelethonListenerHelper(client)
        await helper.record_min_id(entity_a)
        await helper.record_min_id(entity_b)

        collected_a: list[CollectedMessage] = []
        collected_b: list[CollectedMessage] = []
        stop = [False]

        handler_a = helper.make_handler(entity_a, collected_a, stop)
        handler_b = helper.make_handler(entity_b, collected_b, stop)

        # entity_a 핸들러 — min_id=500, msg_id=600 → 수집
        ev_a = _make_fake_event(msg_id=600, text="msg in A")
        ev_a.get_sender = AsyncMock(return_value=_make_bot_sender("bot_a"))
        await handler_a(ev_a)

        # entity_b 핸들러 — min_id=1000, msg_id=600 → skip (600 <= 1000)
        ev_b = _make_fake_event(msg_id=600, text="msg in B")
        ev_b.get_sender = AsyncMock(return_value=_make_bot_sender("bot_b"))
        await handler_b(ev_b)

        assert len(collected_a) == 1  # A 는 수집
        assert len(collected_b) == 0  # B 는 skip (min_id=1000 > 600)

    @pytest.mark.asyncio
    async def test_scenario_boundary_reset(self):
        """시나리오 경계: record_min_id 재호출 시 min_id 갱신 → 이전 시나리오 메시지 제거."""
        client = AsyncMock()
        entity = _make_chat_entity(1)

        # 시나리오 1 설정: min_id = 200
        client.get_messages = AsyncMock(return_value=[_make_fake_message(200)])
        helper = TelethonListenerHelper(client)
        await helper.record_min_id(entity)

        collected1: list[CollectedMessage] = []
        stop = [False]
        handler1 = helper.make_handler(entity, collected1, stop)

        ev_old = _make_fake_event(msg_id=150)
        ev_old.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler1(ev_old)  # 150 <= 200 → skip

        ev_new = _make_fake_event(msg_id=250, text="scenario1 msg")
        ev_new.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler1(ev_new)  # 250 > 200 → collect

        assert len(collected1) == 1

        # 시나리오 2 설정: min_id = 300
        client.get_messages = AsyncMock(return_value=[_make_fake_message(300)])
        await helper.record_min_id(entity)

        collected2: list[CollectedMessage] = []
        handler2 = helper.make_handler(entity, collected2, stop)

        ev_mid = _make_fake_event(msg_id=250, text="same msg from scenario 1")
        ev_mid.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler2(ev_mid)  # 250 <= 300 → skip (시나리오 1 메시지 오염 방지)

        ev_after = _make_fake_event(msg_id=350, text="scenario2 msg")
        ev_after.get_sender = AsyncMock(return_value=_make_bot_sender())
        await handler2(ev_after)  # 350 > 300 → collect

        assert len(collected2) == 1
        assert collected2[0].text == "scenario2 msg"


# ---------------------------------------------------------------------------
# reset() 테스트
# ---------------------------------------------------------------------------


class TestReset:
    @pytest.mark.asyncio
    async def test_reset_specific_chat(self):
        client = _make_client(latest_msg_id=100)
        helper = TelethonListenerHelper(client)
        entity_a = _make_chat_entity(1)
        entity_b = _make_chat_entity(2)

        client.get_messages = AsyncMock(side_effect=[
            [_make_fake_message(100)],
            [_make_fake_message(200)],
        ])
        await helper.record_min_id(entity_a)
        await helper.record_min_id(entity_b)

        helper.reset(entity_a)

        assert helper.get_min_id(entity_a) == 0
        assert helper.get_min_id(entity_b) == 200

    @pytest.mark.asyncio
    async def test_reset_all(self):
        client = AsyncMock()
        client.get_messages = AsyncMock(side_effect=[
            [_make_fake_message(100)],
            [_make_fake_message(200)],
        ])
        helper = TelethonListenerHelper(client)
        entity_a = _make_chat_entity(1)
        entity_b = _make_chat_entity(2)

        await helper.record_min_id(entity_a)
        await helper.record_min_id(entity_b)

        helper.reset()  # 전체 초기화

        assert helper.get_min_id(entity_a) == 0
        assert helper.get_min_id(entity_b) == 0
