"""ACT-4: 태스크 완료 시 notify_task_done() 자동 호출 검증.

검증 대상:
1. _handle_pm_done_event: 모든 siblings done → 합성 후 notify_task_done() 호출
2. _synthesis_poll_loop(간접): notify_task_done이 bus 없을 때 호출 안 됨 (안전성)
3. 합성 실패(예외) 시 notify_task_done() 호출 안 됨 (예외 경로 분리)
4. 형제 태스크 미완료 시 notify_task_done() 호출 안 됨
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.telegram_relay import TelegramRelay
from core.message_bus import MessageBus


def _make_relay(with_bus: bool = True) -> TelegramRelay:
    """테스트용 TelegramRelay 인스턴스 생성."""
    relay = TelegramRelay(
        token="fake",
        allowed_chat_id=999,
        session_manager=MagicMock(),
        memory_manager=MagicMock(),
        org_id="aiorg_pm_bot",
        context_db=MagicMock(),
    )
    relay.allowed_chat_id = 999
    relay._synthesizing: set = set()

    # PM 오케스트레이터 목(mock)
    relay._pm_orchestrator = MagicMock()
    relay._pm_orchestrator._synthesize_and_act = AsyncMock()

    # P2P 메신저 목
    relay._p2p = MagicMock()
    relay._p2p.notify_task_done = AsyncMock(return_value=[])

    # 컨텍스트 DB 목
    relay.context_db = MagicMock()

    # bus
    relay.bus = MessageBus() if with_bus else None

    return relay


# ── TC1: 모든 siblings done → 합성 완료 → notify_task_done() 호출 ──────────

@pytest.mark.asyncio
async def test_handle_pm_done_event_calls_notify_when_all_done() -> None:
    """모든 siblings가 done 상태일 때 합성 후 notify_task_done()이 호출돼야 한다."""
    relay = _make_relay(with_bus=True)

    task_id = "T-pm-001"
    parent_id = "T-parent-001"

    # DB 목: task_info, subtasks 설정
    task_info = {"id": task_id, "parent_id": parent_id}
    siblings = [
        {"id": "T-sub-001", "status": "done"},
        {"id": "T-sub-002", "status": "done"},
    ]
    relay.context_db.get_pm_task = AsyncMock(return_value=task_info)
    relay.context_db.get_subtasks = AsyncMock(return_value=siblings)
    relay._inject_collab_result = AsyncMock()

    text = f"✅ [개발실] 태스크 {task_id} 완료\n작업 끝났습니다."

    # ensure_future를 패치하지 않고 실제 이벤트 루프에서 실행
    await relay._handle_pm_done_event(text)
    # 스케줄된 코루틴이 실행될 수 있도록 이벤트 루프 한 사이클 양보
    await asyncio.sleep(0)

    # _synthesize_and_act가 호출됐는지 확인
    relay._pm_orchestrator._synthesize_and_act.assert_awaited_once_with(
        parent_id, siblings, 999
    )

    # notify_task_done이 올바른 인자로 호출됐는지 확인
    relay._p2p.notify_task_done.assert_awaited_once_with(
        "aiorg_pm_bot", parent_id, "합성 완료"
    )


# ── TC2: bus 없을 때 → notify_task_done() 호출하지 않음 ─────────────────────

@pytest.mark.asyncio
async def test_handle_pm_done_event_no_notify_without_bus() -> None:
    """bus가 None이면 notify_task_done()을 호출하지 않아야 한다."""
    relay = _make_relay(with_bus=False)

    task_id = "T-pm-002"
    parent_id = "T-parent-002"

    task_info = {"id": task_id, "parent_id": parent_id}
    siblings = [{"id": "T-sub-001", "status": "done"}]
    relay.context_db.get_pm_task = AsyncMock(return_value=task_info)
    relay.context_db.get_subtasks = AsyncMock(return_value=siblings)
    relay._inject_collab_result = AsyncMock()

    text = f"✅ [개발실] 태스크 {task_id} 완료"

    await relay._handle_pm_done_event(text)
    await asyncio.sleep(0)

    # bus 없으면 notify_task_done 호출되지 않아야 함
    relay._p2p.notify_task_done.assert_not_awaited()


# ── TC3: 합성 예외 발생 시 → notify_task_done() 호출하지 않음 ────────────────

@pytest.mark.asyncio
async def test_handle_pm_done_event_no_notify_on_synthesis_error() -> None:
    """_synthesize_and_act 예외 발생 시 notify_task_done()은 호출되지 않아야 한다."""
    relay = _make_relay(with_bus=True)

    task_id = "T-pm-003"
    parent_id = "T-parent-003"

    relay._pm_orchestrator._synthesize_and_act = AsyncMock(
        side_effect=RuntimeError("합성 실패 테스트")
    )

    task_info = {"id": task_id, "parent_id": parent_id}
    siblings = [{"id": "T-sub-001", "status": "done"}]
    relay.context_db.get_pm_task = AsyncMock(return_value=task_info)
    relay.context_db.get_subtasks = AsyncMock(return_value=siblings)
    relay._inject_collab_result = AsyncMock()

    text = f"✅ [개발실] 태스크 {task_id} 완료"

    # 예외가 outer try/except에서 잡혀야 함 (크래시 없이)
    await relay._handle_pm_done_event(text)
    await asyncio.sleep(0)

    # 예외 발생 시 notify_task_done() 미호출
    relay._p2p.notify_task_done.assert_not_awaited()


# ── TC4: siblings 미완료 시 → notify_task_done() 호출하지 않음 ───────────────

@pytest.mark.asyncio
async def test_handle_pm_done_event_no_notify_when_siblings_pending() -> None:
    """아직 pending 상태인 sibling이 있으면 notify_task_done()을 호출하지 않아야 한다."""
    relay = _make_relay(with_bus=True)

    task_id = "T-pm-004"
    parent_id = "T-parent-004"

    task_info = {"id": task_id, "parent_id": parent_id}
    siblings = [
        {"id": "T-sub-001", "status": "done"},
        {"id": "T-sub-002", "status": "assigned"},  # 아직 진행 중
    ]
    relay.context_db.get_pm_task = AsyncMock(return_value=task_info)
    relay.context_db.get_subtasks = AsyncMock(return_value=siblings)
    relay._inject_collab_result = AsyncMock()

    text = f"✅ [개발실] 태스크 {task_id} 완료"

    await relay._handle_pm_done_event(text)
    await asyncio.sleep(0)

    # 미완료 siblings 존재 → 합성도, notify도 없어야 함
    relay._pm_orchestrator._synthesize_and_act.assert_not_awaited()
    relay._p2p.notify_task_done.assert_not_awaited()


# ── TC5: parent_id 없는 독립 태스크 → notify_task_done() 호출하지 않음 ────────

@pytest.mark.asyncio
async def test_handle_pm_done_event_no_notify_without_parent() -> None:
    """parent_id가 없는 독립 태스크는 notify_task_done() 미호출."""
    relay = _make_relay(with_bus=True)

    task_id = "T-pm-005"
    task_info = {"id": task_id, "parent_id": None}
    relay.context_db.get_pm_task = AsyncMock(return_value=task_info)
    relay.context_db.get_subtasks = AsyncMock(return_value=[])
    relay._inject_collab_result = AsyncMock()

    text = f"✅ [개발실] 태스크 {task_id} 완료"

    await relay._handle_pm_done_event(text)
    await asyncio.sleep(0)

    relay._p2p.notify_task_done.assert_not_awaited()
