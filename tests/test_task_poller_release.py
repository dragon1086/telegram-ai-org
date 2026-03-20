"""Tests for TaskPoller double-release fix + async wrappers (Cycle 7 US-005)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.task_poller import TaskPoller


def _make_poller(on_task=None) -> tuple[TaskPoller, MagicMock]:
    db = MagicMock()
    db.release_pm_task_lease = AsyncMock()
    poller = TaskPoller(
        context_db=db,
        org_id="test_org",
        on_task=on_task or AsyncMock(),
        lease_ttl_sec=60.0,
        poll_interval=2.0,
    )
    return poller, db


# ---------------------------------------------------------------------------
# TC1: _on_task 성공 + release 자체 실패 → release 1회만 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_double_release_on_release_failure() -> None:
    """_on_task 성공 후 release가 예외를 던져도 재시도 없이 1회만 호출."""
    on_task = AsyncMock()
    poller, db = _make_poller(on_task)

    # release가 예외를 던짐
    db.release_pm_task_lease.side_effect = RuntimeError("DB연결 실패")

    task = {"id": "T-001", "description": "테스트"}
    poller._processing.add("T-001")

    await poller._execute_task(task)

    # release는 정확히 1회만 호출됨
    assert db.release_pm_task_lease.call_count == 1, (
        f"release 1회 기대, 실제: {db.release_pm_task_lease.call_count}"
    )
    # 성공 경로 → requeue_if_running=False
    call_kwargs = db.release_pm_task_lease.call_args.kwargs
    assert call_kwargs.get("requeue_if_running") is False


# ---------------------------------------------------------------------------
# TC2: _on_task 실패 → requeue=True로 1회만 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_double_release_on_task_failure() -> None:
    """_on_task 실패 시 requeue_if_running=True로 release 1회."""
    on_task = AsyncMock(side_effect=ValueError("태스크 실패"))
    poller, db = _make_poller(on_task)

    task = {"id": "T-002", "description": "실패 태스크"}
    poller._processing.add("T-002")

    await poller._execute_task(task)

    assert db.release_pm_task_lease.call_count == 1
    call_kwargs = db.release_pm_task_lease.call_args.kwargs
    assert call_kwargs.get("requeue_if_running") is True


# ---------------------------------------------------------------------------
# TC3: LessonMemory async 래퍼 동작 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lesson_memory_async_wrappers(tmp_path: Path) -> None:
    """arecord, aget_relevant async 메서드가 sync 메서드를 위임."""
    from core.lesson_memory import LessonMemory

    lm = LessonMemory(db_path=tmp_path / "lesson.db")

    lesson = await lm.arecord(
        task_description="테스트 태스크",
        category="timeout",
        what_went_wrong="시간 초과",
        how_to_prevent="타임아웃 설정",
        worker="test_bot",
    )
    assert lesson.category == "timeout"
    assert lesson.worker == "test_bot"

    relevant = await lm.aget_relevant("테스트 태스크")
    assert len(relevant) >= 1
    assert relevant[0].id == lesson.id


# ---------------------------------------------------------------------------
# TC4: ShoutoutSystem async 래퍼 동작 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_shoutout_system_async_wrappers(tmp_path: Path) -> None:
    """agive_shoutout, aweekly_mvp async 메서드가 sync 메서드를 위임."""
    from core.shoutout_system import ShoutoutSystem

    ss = ShoutoutSystem(db_path=tmp_path / "shoutout.db")

    shoutout = await ss.agive_shoutout(
        from_agent="bot_a",
        to_agent="bot_b",
        reason="훌륭한 코드 작성",
        task_id="T-999",
    )
    assert shoutout.from_agent == "bot_a"
    assert shoutout.to_agent == "bot_b"

    mvp = await ss.aweekly_mvp()
    assert mvp == "bot_b"
