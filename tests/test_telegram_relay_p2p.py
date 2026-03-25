"""TelegramRelay._p2p (P2PMessenger 주입) 단위 테스트.

ACT-3: telegram_relay.py에 P2PMessenger 인스턴스 주입 검증.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.message_bus import MessageBus
from core.p2p_messenger import P2PMessenger
from core.telegram_relay import TelegramRelay


def make_relay(bus: MessageBus | None = None) -> TelegramRelay:
    """테스트용 TelegramRelay 인스턴스 생성 헬퍼."""
    return TelegramRelay(
        token="fake-token",
        allowed_chat_id=123456,
        session_manager=MagicMock(),
        memory_manager=MagicMock(),
        org_id="aiorg_engineering_bot",
        context_db=None,
        bus=bus,
    )


# ---------------------------------------------------------------------------
# 주입 구조 검증
# ---------------------------------------------------------------------------


def test_p2p_instance_is_created_on_init() -> None:
    """TelegramRelay 초기화 시 _p2p 속성이 P2PMessenger 인스턴스여야 한다."""
    relay = make_relay()
    assert hasattr(relay, "_p2p"), "_p2p 속성이 없음"
    assert isinstance(relay._p2p, P2PMessenger), "_p2p가 P2PMessenger 타입이 아님"


def test_p2p_receives_bus_when_provided() -> None:
    """bus가 주입되면 P2PMessenger도 동일한 bus를 사용해야 한다."""
    bus = MessageBus()
    relay = make_relay(bus=bus)
    assert relay._p2p._bus is bus, "P2PMessenger의 _bus가 relay.bus와 다름"


def test_p2p_bus_is_none_when_no_bus() -> None:
    """bus 없이 생성하면 P2PMessenger._bus도 None이어야 한다."""
    relay = make_relay(bus=None)
    assert relay._p2p._bus is None, "bus가 None인데 P2PMessenger._bus가 None이 아님"


def test_p2p_is_independent_across_instances() -> None:
    """각 TelegramRelay 인스턴스는 독립적인 P2PMessenger를 가져야 한다."""
    relay_a = make_relay()
    relay_b = make_relay()
    assert relay_a._p2p is not relay_b._p2p, "두 relay가 동일한 P2PMessenger 인스턴스를 공유함"


# ---------------------------------------------------------------------------
# notify_task_done 호출 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p2p_notify_task_done_called_directly() -> None:
    """주입된 _p2p 인스턴스의 notify_task_done을 직접 호출할 수 있어야 한다."""
    bus = MessageBus()
    relay = make_relay(bus=bus)

    received = []

    async def handler(msg):
        received.append(msg)

    relay._p2p.register("other_bot", handler)

    msgs = await relay._p2p.notify_task_done(
        from_bot=relay.org_id,
        task_id="T-test-001",
        result_summary="테스트 완료",
        notify_bots=["other_bot"],
    )

    assert len(msgs) == 1, "notify_task_done이 메시지를 1개 반환해야 함"
    assert len(received) == 1, "핸들러가 1회 호출되어야 함"
    assert received[0].payload["type"] == "task_done"
    assert received[0].payload["task_id"] == "T-test-001"
    assert received[0].payload["summary"] == "테스트 완료"
    assert received[0].from_bot == relay.org_id


@pytest.mark.asyncio
async def test_p2p_send_and_receive() -> None:
    """_p2p.send() 로 직접 메시지 전송 후 핸들러 수신 확인."""
    relay = make_relay()

    received = []

    async def handler(msg):
        received.append(msg)

    relay._p2p.register("target_bot", handler)

    msg = await relay._p2p.send(
        from_bot=relay.org_id,
        to_bot="target_bot",
        payload={"type": "collab_request", "task": "코드 리뷰"},
    )

    assert msg.from_bot == relay.org_id
    assert msg.to_bot == "target_bot"
    assert len(received) == 1


@pytest.mark.asyncio
async def test_p2p_list_bots_after_register() -> None:
    """register 후 list_bots()에 봇 이름이 포함되어야 한다."""
    relay = make_relay()

    async def noop(msg):
        pass

    relay._p2p.register("bot_alpha", noop)
    relay._p2p.register("bot_beta", noop)

    bots = relay._p2p.list_bots()
    assert "bot_alpha" in bots
    assert "bot_beta" in bots
