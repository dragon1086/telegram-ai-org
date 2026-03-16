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
import os
import socket
import uuid
from typing import Callable, Awaitable

from loguru import logger

from core.context_db import ContextDB

# 기본 폴링 간격 (초)
DEFAULT_POLL_INTERVAL = 10.0  # 의존성 체인 중간 태스크 감지 (PM_DONE은 최종 합성만 처리)
DEFAULT_LEASE_TTL_SEC = 180.0
DEFAULT_HEARTBEAT_INTERVAL_SEC = 30.0


class TaskPoller:
    """ContextDB 폴링으로 부서봇에 배정된 태스크를 감지·전달."""

    def __init__(
        self,
        context_db: ContextDB,
        org_id: str,
        on_task: Callable[[dict], Awaitable[None]],
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        lease_ttl_sec: float = DEFAULT_LEASE_TTL_SEC,
        heartbeat_interval_sec: float = DEFAULT_HEARTBEAT_INTERVAL_SEC,
    ):
        self._db = context_db
        self._org_id = org_id
        self._on_task = on_task
        self._poll_interval = poll_interval
        self._lease_ttl_sec = lease_ttl_sec
        self._heartbeat_interval_sec = heartbeat_interval_sec
        self._running = False
        self._task: asyncio.Task | None = None
        # 이미 처리 시작한 태스크 ID 추적 (중복 실행 방지)
        self._processing: set[str] = set()
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}
        self._worker_id = f"{org_id}:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

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
        for hb_task in self._heartbeat_tasks.values():
            if not hb_task.done():
                hb_task.cancel()
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
            claimed = await self._db.claim_pm_task_lease(task_id, self._worker_id, self._lease_ttl_sec)
            if claimed is None:
                continue
            self._processing.add(task_id)
            logger.info(f"[TaskPoller:{self._org_id}] 태스크 감지: {task_id}")
            self._heartbeat_tasks[task_id] = asyncio.create_task(self._heartbeat_loop(task_id))
            # 비동기로 태스크 처리 (폴링 루프를 블로킹하지 않음)
            asyncio.create_task(self._execute_task(claimed))

    async def _heartbeat_loop(self, task_id: str) -> None:
        try:
            while self._running and task_id in self._processing:
                await asyncio.sleep(self._heartbeat_interval_sec)
                await self._db.heartbeat_pm_task_lease(task_id, self._worker_id, self._lease_ttl_sec)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(f"[TaskPoller:{self._org_id}] heartbeat 오류: {task_id}")

    async def _execute_task(self, task: dict) -> None:
        """태스크 콜백 실행 및 완료 후 processing set에서 제거."""
        task_id = task["id"]
        released = False
        try:
            await self._on_task(task)
            await self._db.release_pm_task_lease(task_id, self._worker_id, requeue_if_running=False)
            released = True
        except Exception:
            logger.exception(f"[TaskPoller:{self._org_id}] 태스크 실행 오류: {task_id}")
            await self._db.release_pm_task_lease(
                task_id,
                self._worker_id,
                requeue_if_running=True,
                retry_delay_seconds=max(self._lease_ttl_sec, self._poll_interval * 4),
            )
            released = True
        finally:
            self._processing.discard(task_id)
            hb_task = self._heartbeat_tasks.pop(task_id, None)
            if hb_task and not hb_task.done():
                hb_task.cancel()
            if not released:
                await self._db.release_pm_task_lease(task_id, self._worker_id, requeue_if_running=True)
