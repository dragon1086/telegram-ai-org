"""자율 협업 시스템 E2E 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from core.collab_request import is_collab_request, make_collab_request
from core.collaboration_tracker import CollaborationTracker
from core.message_bus import MessageBus
from core.p2p_messenger import P2PMessage, P2PMessenger
from core.shoutout_system import ShoutoutSystem


# ---------------------------------------------------------------------------
# TC-D1: P2PMessenger.send() → 핸들러 수신 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc_d1_p2p_send_delivers_to_handler() -> None:
    bus = MessageBus()
    messenger = P2PMessenger(bus=bus)

    handler = AsyncMock()
    messenger.register("bot_b", handler)

    await messenger.send("bot_a", "bot_b", {"type": "hello"})

    handler.assert_called_once()
    msg: P2PMessage = handler.call_args[0][0]
    assert msg.from_bot == "bot_a"
    assert msg.to_bot == "bot_b"
    assert msg.payload["type"] == "hello"


# ---------------------------------------------------------------------------
# TC-D2: broadcast() → 등록된 모든 봇 수신 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc_d2_broadcast_reaches_all_registered() -> None:
    bus = MessageBus()
    messenger = P2PMessenger(bus=bus)

    received: list[str] = []

    async def make_handler(name: str):
        async def handler(msg: P2PMessage) -> None:
            received.append(name)
        return handler

    messenger.register("bot_b", await make_handler("bot_b"))
    messenger.register("bot_c", await make_handler("bot_c"))

    await messenger.broadcast("bot_a", {"type": "announce"})

    assert "bot_b" in received
    assert "bot_c" in received


# ---------------------------------------------------------------------------
# TC-D3: CollaborationTracker.record() 3회 (동일 pair) → get_frequent_pairs() 반환
# ---------------------------------------------------------------------------


def test_tc_d3_frequent_pairs_tracked(
    collaboration_tracker: CollaborationTracker,
) -> None:
    for i in range(3):
        collaboration_tracker.record(
            task_id=f"task-{i}",
            participants=["bot_a", "bot_b"],
            task_type="coding",
            success=True,
        )

    pairs = collaboration_tracker.get_frequent_pairs(min_count=2)

    assert len(pairs) > 0, "frequent pairs가 비어 있음"
    pair_keys = [pair for pair, count in pairs]
    assert ("bot_a", "bot_b") in pair_keys or ("bot_b", "bot_a") in pair_keys, (
        f"(bot_a, bot_b) 쌍이 없음: {pair_keys}"
    )


# ---------------------------------------------------------------------------
# TC-D4: ShoutoutSystem에 shoutout 기록 후 get_top_recipients() 검증
# ---------------------------------------------------------------------------


def test_tc_d4_shoutout_top_recipients(shoutout_system: ShoutoutSystem) -> None:
    shoutout_system.give_shoutout("bot_a", "bot_b", "잘했어요", task_id="t-1")
    shoutout_system.give_shoutout("bot_a", "bot_b", "훌륭해요", task_id="t-2")
    shoutout_system.give_shoutout("bot_c", "bot_b", "최고예요", task_id="t-3")

    top = shoutout_system.get_top_recipients(days=7)

    assert len(top) > 0, "top_recipients가 비어 있음"
    top_agent, top_count = top[0]
    assert top_agent == "bot_b", f"최상위 수신자가 bot_b가 아님: {top_agent}"
    assert top_count == 3


# ---------------------------------------------------------------------------
# TC-D5: is_collab_request 감지 테스트
# ---------------------------------------------------------------------------


def test_tc_d5_is_collab_request_detection() -> None:
    valid_msg = make_collab_request(task="시장 조사 필요", from_org="bot_a")
    plain_text = "안녕하세요 일반 메시지입니다"

    assert is_collab_request(valid_msg) is True, "협업 요청 메시지가 감지되지 않음"
    assert is_collab_request(plain_text) is False, "일반 텍스트가 협업 요청으로 감지됨"


# ---------------------------------------------------------------------------
# TC-D6: ShoutoutSystem에 to_agent='bot_a' 5회 기록 → weekly_mvp() == 'bot_a'
# ---------------------------------------------------------------------------


def test_tc_d6_weekly_mvp(shoutout_system: ShoutoutSystem) -> None:
    for i in range(5):
        shoutout_system.give_shoutout(
            from_agent=f"bot_{i}",
            to_agent="bot_a",
            reason="이번 주 MVP!",
            task_id=f"task-{i}",
        )

    mvp = shoutout_system.weekly_mvp()

    assert mvp == "bot_a", f"weekly_mvp()가 'bot_a'가 아님: {mvp}"
