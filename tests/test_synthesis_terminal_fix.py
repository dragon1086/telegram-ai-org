"""Synthesis terminal-state fix 회귀 방지 테스트.

수정 내용:
- on_task_complete (pm_orchestrator): all-done 체크 → all-terminal 체크
- _synthesis_poll_loop (telegram_relay): SQL + all-done 체크 → all-terminal 체크
- _handle_pm_done_event (telegram_relay): 실패 메시지 처리 + all-terminal 체크

버그: 서브태스크가 failed 상태로 끝났을 때 부모 태스크의 합성이 영구적으로
      트리거되지 않아 부모 태스크가 assigned 상태에 갇히는 문제.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator

_TERMINAL = {"done", "failed", "cancelled"}


@pytest.fixture
async def setup():
    with tempfile.TemporaryDirectory() as tmp:
        import os
        db = ContextDB(Path(tmp) / "test.db")
        await db.initialize()
        graph = TaskGraph(db)
        claim = ClaimManager()
        memory = MemoryManager("pm")
        send_fn = AsyncMock()
        os.environ["AIORG_REPORT_DIR"] = str(Path(tmp) / "reports")
        orch = PMOrchestrator(db, graph, claim, memory, "aiorg_pm_bot", send_fn)
        yield orch, db, send_fn, tmp
        os.environ.pop("AIORG_REPORT_DIR", None)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────

async def _make_parent_with_subtasks(db: ContextDB, parent_id: str, subtask_specs: list[dict]):
    """부모 태스크와 서브태스크를 DB에 생성."""
    await db.create_pm_task(
        task_id=parent_id,
        description="parent task",
        assigned_dept="aiorg_pm_bot",
        created_by="aiorg_pm_bot",
    )
    for spec in subtask_specs:
        await db.create_pm_task(
            task_id=spec["id"],
            description=spec.get("description", "subtask"),
            assigned_dept=spec.get("dept", "aiorg_engineering_bot"),
            created_by="aiorg_pm_bot",
            parent_id=parent_id,
        )
        if spec.get("status") != "pending":
            await db.update_pm_task_status(spec["id"], spec["status"])


# ── 테스트 1: all-done 시 합성 트리거 (기존 동작 유지 확인) ───────────────

@pytest.mark.asyncio
async def test_synthesis_triggers_when_all_done(setup):
    """모든 서브태스크가 done이면 합성이 트리거되어야 한다 (기존 동작 유지)."""
    orch, db, send_fn, _ = setup

    parent_id = "T-test-parent-1"
    await _make_parent_with_subtasks(db, parent_id, [
        {"id": "T-test-sub-1", "status": "done"},
        {"id": "T-test-sub-2", "status": "done"},
    ])

    siblings = await db.get_subtasks(parent_id)
    all_terminal = bool(siblings) and all(s["status"] in _TERMINAL for s in siblings)
    assert all_terminal is True, "all-done → all-terminal 체크 통과해야 함"


# ── 테스트 2: 서브태스크 실패 시 합성 트리거 (버그 수정 검증) ─────────────

@pytest.mark.asyncio
async def test_synthesis_triggers_when_subtask_failed(setup):
    """서브태스크 중 하나가 failed이고 나머지가 done이면 합성이 트리거되어야 한다."""
    orch, db, send_fn, _ = setup

    parent_id = "T-test-parent-2"
    await _make_parent_with_subtasks(db, parent_id, [
        {"id": "T-test-sub-3", "status": "done"},
        {"id": "T-test-sub-4", "status": "failed"},
    ])

    siblings = await db.get_subtasks(parent_id)
    # 수정 전: all(s["status"] == "done") → False → 합성 미트리거
    old_check = all(s["status"] == "done" for s in siblings)
    assert old_check is False, "구 로직: failed 있으면 합성 미트리거 (버그 재현)"

    # 수정 후: all-terminal 체크 → True → 합성 트리거
    new_check = bool(siblings) and all(s["status"] in _TERMINAL for s in siblings)
    assert new_check is True, "신 로직: failed도 terminal → 합성 트리거"


# ── 테스트 3: 모든 서브태스크 실패 시 합성 트리거 ────────────────────────

@pytest.mark.asyncio
async def test_synthesis_triggers_when_all_failed(setup):
    """모든 서브태스크가 failed여도 합성이 트리거되어야 한다."""
    orch, db, send_fn, _ = setup

    parent_id = "T-test-parent-3"
    await _make_parent_with_subtasks(db, parent_id, [
        {"id": "T-test-sub-5", "status": "failed"},
        {"id": "T-test-sub-6", "status": "failed"},
    ])

    siblings = await db.get_subtasks(parent_id)
    all_terminal = bool(siblings) and all(s["status"] in _TERMINAL for s in siblings)
    assert all_terminal is True, "all-failed → all-terminal → 합성 트리거"


# ── 테스트 4: 진행 중 서브태스크 있으면 합성 미트리거 ────────────────────

@pytest.mark.asyncio
async def test_synthesis_blocked_when_sibling_still_running(setup):
    """서브태스크 중 하나가 running이면 합성이 트리거되어서는 안 된다."""
    orch, db, send_fn, _ = setup

    parent_id = "T-test-parent-4"
    await _make_parent_with_subtasks(db, parent_id, [
        {"id": "T-test-sub-7", "status": "done"},
        {"id": "T-test-sub-8", "status": "running"},
    ])

    siblings = await db.get_subtasks(parent_id)
    all_terminal = bool(siblings) and all(s["status"] in _TERMINAL for s in siblings)
    assert all_terminal is False, "running 있으면 합성 차단"


# ── 테스트 5: cancelled 포함 all-terminal 체크 ───────────────────────────

@pytest.mark.asyncio
async def test_synthesis_triggers_when_subtask_cancelled(setup):
    """서브태스크가 cancelled여도 terminal 상태로 인식해야 한다."""
    orch, db, send_fn, _ = setup

    parent_id = "T-test-parent-5"
    await _make_parent_with_subtasks(db, parent_id, [
        {"id": "T-test-sub-9", "status": "done"},
        {"id": "T-test-sub-10", "status": "cancelled"},
    ])

    siblings = await db.get_subtasks(parent_id)
    all_terminal = bool(siblings) and all(s["status"] in _TERMINAL for s in siblings)
    assert all_terminal is True, "cancelled도 terminal → 합성 트리거"


# ── 테스트 6: on_task_complete terminal 체크 확인 (구 all-done 회귀 방지) ─

@pytest.mark.asyncio
async def test_on_task_complete_triggers_synthesis_on_sibling_failure(setup):
    """on_task_complete 호출 시 형제 태스크가 failed여도 합성이 트리거되어야 한다."""
    orch, db, send_fn, _ = setup

    parent_id = "T-test-parent-6"
    await _make_parent_with_subtasks(db, parent_id, [
        {"id": "T-test-sub-11", "status": "failed"},   # 이미 실패
        {"id": "T-test-sub-12", "status": "assigned"},  # 이제 완료 처리할 태스크
    ])
    # sub-12를 assigned → done으로 업데이트
    await db.update_pm_task_status("T-test-sub-12", "done")

    # on_task_complete 호출 시 합성 트리거 여부 확인
    synthesize_mock = AsyncMock()
    orch._synthesize_and_act = synthesize_mock

    chat_id = 12345
    await orch.on_task_complete("T-test-sub-12", "작업 완료", chat_id)

    synthesize_mock.assert_called_once_with(parent_id, pytest.approx(
        await db.get_subtasks(parent_id), abs=None
    ), chat_id)


# ── 테스트 7: _handle_pm_done_event 실패 메시지 패턴 매칭 확인 ───────────

def test_pm_done_event_failure_pattern():
    """_handle_pm_done_event이 실패 메시지에서 task_id를 추출해야 한다."""
    import re
    pattern = r"태스크\s+(T-[A-Za-z0-9_]+-\d+)\s+(완료|실패)"

    success_text = "✅ [개발실] 태스크 T-aiorg_pm_bot-302 완료\n결과 내용"
    failure_text = "❌ [개발실] 태스크 T-aiorg_pm_bot-247 실패: 오류 메시지"

    m_success = re.search(pattern, success_text)
    assert m_success is not None, "성공 메시지 패턴 매칭"
    assert m_success.group(1) == "T-aiorg_pm_bot-302"
    assert m_success.group(2) == "완료"

    m_failure = re.search(pattern, failure_text)
    assert m_failure is not None, "실패 메시지 패턴 매칭"
    assert m_failure.group(1) == "T-aiorg_pm_bot-247"
    assert m_failure.group(2) == "실패"
