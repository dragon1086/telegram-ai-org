"""태스크 상태 추적."""
from __future__ import annotations

import asyncio
from datetime import datetime
from enum import Enum
from typing import Callable

from loguru import logger
from pydantic import BaseModel


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"           # 신규
    RUNNING = "running"
    WAITING_ACK = "waiting_ack"  # 완료 확인 대기
    REWORK = "rework"               # 신규
    DONE = "done"
    FAILED = "failed"
    CLOSED = "closed"  # 모든 봇 확인 완료
    CANCELLED = "cancelled"         # 신규


VALID_TRANSITIONS: dict[TaskStatus, list[TaskStatus]] = {
    TaskStatus.PENDING: [TaskStatus.ASSIGNED, TaskStatus.RUNNING, TaskStatus.WAITING_ACK, TaskStatus.FAILED, TaskStatus.CLOSED, TaskStatus.CANCELLED],
    TaskStatus.ASSIGNED: [TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.RUNNING: [TaskStatus.WAITING_ACK, TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.WAITING_ACK: [TaskStatus.DONE, TaskStatus.CLOSED, TaskStatus.REWORK, TaskStatus.CANCELLED],
    TaskStatus.REWORK: [TaskStatus.RUNNING, TaskStatus.CANCELLED],
}

# Terminal states — no outgoing transitions allowed
_TERMINAL_STATES = {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CLOSED, TaskStatus.CANCELLED}


class Task(BaseModel):
    """단일 태스크."""

    id: str
    description: str
    assigned_to: list[str]  # 할당된 봇 핸들 목록
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    result: str | None = None
    acks: list[str] = []  # 완료 확인한 봇 목록
    parent_id: str | None = None

    def model_post_init(self, __context: object) -> None:
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    def all_acked(self) -> bool:
        """모든 할당 봇이 완료를 확인했는지."""
        return set(self.assigned_to) <= set(self.acks)


class TaskManager:
    """태스크 생명주기 관리."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._counter = 0
        self._lock = asyncio.Lock()
        self._status_callbacks: list[Callable[[Task], None]] = []

    def on_status_change(self, callback: Callable[[Task], None]) -> None:
        """태스크 상태 변경 시 콜백 등록."""
        self._status_callbacks.append(callback)

    async def create_task(self, description: str, assigned_to: list[str], parent_id: str | None = None) -> Task:
        """새 태스크 생성."""
        async with self._lock:
            self._counter += 1
            task_id = f"T{self._counter:03d}"
            task = Task(id=task_id, description=description, assigned_to=assigned_to, parent_id=parent_id)
            self._tasks[task_id] = task
            logger.info(f"태스크 생성: {task_id} → {assigned_to}")
            return task

    async def update_status(self, task_id: str, status: TaskStatus, result: str | None = None) -> Task:
        """태스크 상태 업데이트."""
        async with self._lock:
            task = self._tasks[task_id]
            if task.status in _TERMINAL_STATES:
                raise ValueError(f"Invalid transition: {task.status.value} -> {status.value}")
            valid = VALID_TRANSITIONS.get(task.status, [])
            if valid and status not in valid:
                raise ValueError(f"Invalid transition: {task.status.value} -> {status.value}")
            task.status = status
            now = datetime.utcnow().isoformat()
            if status == TaskStatus.RUNNING:
                task.started_at = now
            elif status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CLOSED, TaskStatus.CANCELLED):
                task.completed_at = now
            if result:
                task.result = result
            logger.info(f"태스크 상태: {task_id} → {status}")
            for cb in self._status_callbacks:
                cb(task)
            return task

    async def record_ack(self, task_id: str, bot_handle: str) -> Task:
        """봇의 완료 확인 기록."""
        async with self._lock:
            task = self._tasks[task_id]
            if bot_handle not in task.acks:
                task.acks.append(bot_handle)
            logger.info(f"ACK 수신: {task_id} ← {bot_handle} ({len(task.acks)}/{len(task.assigned_to)})")
            return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def get_active_tasks(self) -> list[Task]:
        return [t for t in self._tasks.values()
                if t.status not in (TaskStatus.CLOSED, TaskStatus.FAILED, TaskStatus.CANCELLED)]

    async def update_parent_status(self, parent_id: str) -> None:
        """자식 태스크 상태를 집계하여 부모 상태 자동 갱신."""
        children = [t for t in self._tasks.values() if t.parent_id == parent_id]
        if not children:
            return
        if any(c.status == TaskStatus.FAILED for c in children):
            await self.update_status(parent_id, TaskStatus.FAILED)
        elif all(c.status == TaskStatus.DONE for c in children):
            await self.update_status(parent_id, TaskStatus.WAITING_ACK)
        # 그 외 (일부 진행 중) -> 변경 없음
