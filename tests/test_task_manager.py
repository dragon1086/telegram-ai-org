"""TaskManager 단위 테스트 — Phase 1 이식 전 회귀 보호."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task_manager import Task, TaskManager, TaskStatus


@pytest.mark.asyncio
async def test_create_task_returns_pending():
    tm = TaskManager()
    task = await tm.create_task("test task", ["@bot1"])
    assert task.status == TaskStatus.PENDING
    assert task.id == "T001"
    assert task.assigned_to == ["@bot1"]


@pytest.mark.asyncio
async def test_create_task_increments_counter():
    tm = TaskManager()
    t1 = await tm.create_task("task 1", ["@bot1"])
    t2 = await tm.create_task("task 2", ["@bot2"])
    assert t1.id == "T001"
    assert t2.id == "T002"


@pytest.mark.asyncio
async def test_update_status_to_running():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    updated = await tm.update_status(task.id, TaskStatus.RUNNING)
    assert updated.status == TaskStatus.RUNNING
    assert updated.started_at is not None


@pytest.mark.asyncio
async def test_update_status_to_done_sets_completed_at():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    await tm.update_status(task.id, TaskStatus.RUNNING)
    updated = await tm.update_status(task.id, TaskStatus.DONE, result="완료")
    assert updated.status == TaskStatus.DONE
    assert updated.completed_at is not None
    assert updated.result == "완료"


@pytest.mark.asyncio
async def test_update_status_triggers_callback():
    tm = TaskManager()
    called_with = []
    tm.on_status_change(lambda t: called_with.append(t.status))
    task = await tm.create_task("test", ["@bot1"])
    await tm.update_status(task.id, TaskStatus.RUNNING)
    assert TaskStatus.RUNNING in called_with


@pytest.mark.asyncio
async def test_record_ack():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1", "@bot2"])
    await tm.record_ack(task.id, "@bot1")
    updated = tm.get_task(task.id)
    assert "@bot1" in updated.acks
    assert not updated.all_acked()


@pytest.mark.asyncio
async def test_record_ack_duplicate_ignored():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    await tm.record_ack(task.id, "@bot1")
    await tm.record_ack(task.id, "@bot1")
    assert tm.get_task(task.id).acks.count("@bot1") == 1


@pytest.mark.asyncio
async def test_all_acked():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1", "@bot2"])
    await tm.record_ack(task.id, "@bot1")
    await tm.record_ack(task.id, "@bot2")
    assert tm.get_task(task.id).all_acked()


@pytest.mark.asyncio
async def test_get_active_tasks():
    tm = TaskManager()
    t1 = await tm.create_task("active", ["@bot1"])
    t2 = await tm.create_task("done", ["@bot2"])
    await tm.update_status(t2.id, TaskStatus.CLOSED)
    active = tm.get_active_tasks()
    assert len(active) == 1
    assert active[0].id == t1.id


@pytest.mark.asyncio
async def test_get_active_excludes_failed():
    tm = TaskManager()
    t1 = await tm.create_task("ok", ["@bot1"])
    t2 = await tm.create_task("fail", ["@bot2"])
    await tm.update_status(t2.id, TaskStatus.FAILED)
    active = tm.get_active_tasks()
    assert len(active) == 1
    assert active[0].id == t1.id


# ---------------------------------------------------------------------------
# Phase 1: 상태 전이 규칙 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_transition_pending_to_assigned():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    updated = await tm.update_status(task.id, TaskStatus.ASSIGNED)
    assert updated.status == TaskStatus.ASSIGNED


@pytest.mark.asyncio
async def test_valid_transition_pending_to_running_backward_compat():
    """기존 코드 호환: PENDING->RUNNING 직접 전이 허용."""
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    updated = await tm.update_status(task.id, TaskStatus.RUNNING)
    assert updated.status == TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_invalid_transition_done_to_running():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    await tm.update_status(task.id, TaskStatus.RUNNING)
    await tm.update_status(task.id, TaskStatus.WAITING_ACK)
    await tm.update_status(task.id, TaskStatus.DONE)
    with pytest.raises(ValueError, match="Invalid transition"):
        await tm.update_status(task.id, TaskStatus.RUNNING)


@pytest.mark.asyncio
async def test_invalid_transition_closed_to_running():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    await tm.update_status(task.id, TaskStatus.RUNNING)
    await tm.update_status(task.id, TaskStatus.WAITING_ACK)
    await tm.update_status(task.id, TaskStatus.CLOSED)
    with pytest.raises(ValueError, match="Invalid transition"):
        await tm.update_status(task.id, TaskStatus.RUNNING)


@pytest.mark.asyncio
async def test_rework_cycle():
    """WAITING_ACK -> REWORK -> RUNNING -> WAITING_ACK."""
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    await tm.update_status(task.id, TaskStatus.RUNNING)
    await tm.update_status(task.id, TaskStatus.WAITING_ACK)
    await tm.update_status(task.id, TaskStatus.REWORK)
    assert tm.get_task(task.id).status == TaskStatus.REWORK
    await tm.update_status(task.id, TaskStatus.RUNNING)
    assert tm.get_task(task.id).status == TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_cancel_from_any_non_terminal():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    await tm.update_status(task.id, TaskStatus.CANCELLED)
    assert tm.get_task(task.id).status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_from_running():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    await tm.update_status(task.id, TaskStatus.RUNNING)
    await tm.update_status(task.id, TaskStatus.CANCELLED)
    assert tm.get_task(task.id).status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancelled_is_terminal():
    tm = TaskManager()
    task = await tm.create_task("test", ["@bot1"])
    await tm.update_status(task.id, TaskStatus.CANCELLED)
    with pytest.raises(ValueError, match="Invalid transition"):
        await tm.update_status(task.id, TaskStatus.RUNNING)


@pytest.mark.asyncio
async def test_get_active_excludes_cancelled():
    tm = TaskManager()
    t1 = await tm.create_task("ok", ["@bot1"])
    t2 = await tm.create_task("cancel", ["@bot2"])
    await tm.update_status(t2.id, TaskStatus.CANCELLED)
    active = tm.get_active_tasks()
    assert len(active) == 1
    assert active[0].id == t1.id
