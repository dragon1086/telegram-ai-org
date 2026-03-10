"""CompletionProtocol 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.completion import CompletionProtocol
from core.task_manager import Task, TaskManager, TaskStatus


async def _make_task(tm: TaskManager, assigned_to: list[str]) -> Task:
    return await tm.create_task("테스트 태스크", assigned_to)


# ---------------------------------------------------------------------------
# initiate_completion → WAITING_ACK
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_initiate_completion_sets_waiting_ack():
    tm = TaskManager()
    send_fn = AsyncMock()
    proto = CompletionProtocol(tm, send_fn)

    task = await _make_task(tm, ["@cokac", "@researcher"])
    await proto.initiate_completion(task)

    updated = tm.get_task(task.id)
    assert updated.status == TaskStatus.WAITING_ACK
    send_fn.assert_awaited_once()


@pytest.mark.asyncio
async def test_initiate_completion_sends_message_with_task_id():
    tm = TaskManager()
    send_fn = AsyncMock()
    proto = CompletionProtocol(tm, send_fn)

    task = await _make_task(tm, ["@cokac"])
    await proto.initiate_completion(task)

    call_arg = send_fn.call_args[0][0]
    assert task.id in call_arg


# ---------------------------------------------------------------------------
# receive_ack — 모두 ack → CLOSED
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_receive_ack_all_closed():
    tm = TaskManager()
    send_fn = AsyncMock()
    proto = CompletionProtocol(tm, send_fn)

    task = await _make_task(tm, ["@cokac", "@researcher"])
    await tm.update_status(task.id, TaskStatus.WAITING_ACK)

    r1 = await proto.receive_ack(task.id, "@cokac")
    assert r1 is False  # 아직 한 명 남음

    r2 = await proto.receive_ack(task.id, "@researcher")
    assert r2 is True  # 전원 확인 → CLOSED

    closed_task = tm.get_task(task.id)
    assert closed_task.status == TaskStatus.CLOSED


# ---------------------------------------------------------------------------
# receive_ack — 부분 ack → 아직 CLOSED 아님
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_receive_ack_partial_not_closed():
    tm = TaskManager()
    send_fn = AsyncMock()
    proto = CompletionProtocol(tm, send_fn)

    task = await _make_task(tm, ["@cokac", "@researcher", "@writer"])
    await tm.update_status(task.id, TaskStatus.WAITING_ACK)

    result = await proto.receive_ack(task.id, "@cokac")
    assert result is False

    still_open = tm.get_task(task.id)
    assert still_open.status != TaskStatus.CLOSED


# ---------------------------------------------------------------------------
# 중복 ack → 무시 (한 번만 기록)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_receive_ack_duplicate_ignored():
    tm = TaskManager()
    send_fn = AsyncMock()
    proto = CompletionProtocol(tm, send_fn)

    task = await _make_task(tm, ["@cokac"])
    await tm.update_status(task.id, TaskStatus.WAITING_ACK)

    await proto.receive_ack(task.id, "@cokac")
    await proto.receive_ack(task.id, "@cokac")  # 중복

    final = tm.get_task(task.id)
    assert final.acks.count("@cokac") == 1
