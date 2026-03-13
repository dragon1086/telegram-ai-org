"""TaskPoller — 부서봇이 ContextDB를 폴링하여 배정된 태스크를 자동 수신.

Telegram Bot API는 봇→봇 메시지를 수신할 수 없으므로,
PM이 ContextDB에 'assigned' 상태로 저장한 태스크를 부서봇이 직접 폴링한다.

Usage:
    poller = TaskPoller(context_db, org_id, on_task_callback)
    poller.start()   # asyncio background task
    poller.stop()    # graceful shutdown
"""
from __future__ import annotations

import asyncio
from typing import Callable, Awaitable

from loguru import logger

from core.context_db import ContextDB

# 기본 폴링 간격 (초)
DEFAULT_POLL_INTERVAL = 10.0  # 의존성 체인 중간 태스크 감지 (PM_DONE은 최종 합성만 처리)


class TaskPoller:
    """ContextDB 폴링으로 부서봇에 배정된 태스크를 감지·전달."""

    def __init__(
        self,
        context_db: ContextDB,
        org_id: str,
        on_task: Callable[[dict], Awaitable[None]],
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ):
        self._db = context_db
        self._org_id = org_id
        self._on_task = on_task
        self._poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None
        # 이미 처리 시작한 태스크 ID 추적 (중복 실행 방지)
        self._processing: set[str] = set()

    def start(self) -> None:
        """백그라운드 폴링 시작."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"[TaskPoller:{self._org_id}] 폴링 시작 (간격={self._poll_interval}s)")

    def stop(self) -> None:
        """폴링 중지."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info(f"[TaskPoller:{self._org_id}] 폴링 중지")

    async def _poll_loop(self) -> None:
        """주기적으로 ContextDB에서 배정된 태스크를 확인."""
        while self._running:
            try:
                await self._check_for_tasks()
            except Exception:
                logger.exception(f"[TaskPoller:{self._org_id}] 폴링 오류")
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

    async def _check_for_tasks(self) -> None:
        """assigned 상태인 태스크를 찾아 콜백 실행."""
        tasks = await self._db.get_tasks_for_dept(self._org_id, status="assigned")
        for task in tasks:
            task_id = task["id"]
            if task_id in self._processing:
                continue
            self._processing.add(task_id)
            # 즉시 running으로 마킹하여 다음 폴링에서 재감지 방지
            await self._db.update_pm_task_status(task_id, "running")
            logger.info(f"[TaskPoller:{self._org_id}] 태스크 감지: {task_id}")
            # 비동기로 태스크 처리 (폴링 루프를 블로킹하지 않음)
            asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: dict) -> None:
        """태스크 콜백 실행 및 완료 후 processing set에서 제거."""
        task_id = task["id"]
        try:
            await self._on_task(task)
        except Exception:
            logger.exception(f"[TaskPoller:{self._org_id}] 태스크 실행 오류: {task_id}")
        finally:
            self._processing.discard(task_id)
