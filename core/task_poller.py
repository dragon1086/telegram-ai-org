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
import time
import uuid
from typing import Callable, Awaitable

from loguru import logger

from core.context_db import ContextDB

# 기본 폴링 간격 (초)
DEFAULT_POLL_INTERVAL = 2.0  # 의존성 체인 중간 태스크 감지 (PM_DONE은 최종 합성만 처리)
DEFAULT_LEASE_TTL_SEC = 180.0
DEFAULT_HEARTBEAT_INTERVAL_SEC = 30.0
# Fast-failure 감지: 짧은 시간에 연속 실패 시 백오프
FAST_FAIL_WINDOW_SEC = 60.0  # 이 시간 내 연속 실패 횟수 추적
FAST_FAIL_THRESHOLD = 3  # 이 횟수 이상이면 백오프 적용
FAST_FAIL_BACKOFF_SEC = 30.0  # 일반 실패 백오프 시간
# 토큰/레이트 리밋 에러 감지 시 장기 백오프
TOKEN_LIMIT_BACKOFF_SEC = 600.0  # 10분 — 토큰 한도는 보통 수십분~1시간 후 풀림
TOKEN_LIMIT_KEYWORDS = (
    "token", "rate_limit", "rate limit", "overloaded", "429",
    "quota", "capacity", "throttl", "too many requests",
    "context window", "max_tokens_exceeded",
)


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
        # Fast-failure 감지: 태스크별 최근 실패 타임스탬프
        self._fail_timestamps: dict[str, list[float]] = {}

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
        # ── 시작 시 stale 태스크 복구 ──
        # run_polling() 재시작으로 죽은 태스크를 assigned로 되돌린다.
        try:
            recovered = await self._db.recover_stale_dept_tasks(
                self._org_id, stale_seconds=self._lease_ttl_sec + 60,
            )
            if recovered:
                logger.info(
                    f"[TaskPoller:{self._org_id}] 시작 시 stale 태스크 {recovered}건 복구 완료"
                )
        except Exception:
            logger.exception(f"[TaskPoller:{self._org_id}] stale 태스크 복구 오류")

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

    def _is_fast_failing(self, task_id: str) -> bool:
        """태스크가 짧은 시간 내 반복 실패 중인지 감지."""
        timestamps = self._fail_timestamps.get(task_id, [])
        if not timestamps:
            return False
        now = time.monotonic()
        # 윈도우 내 실패만 유지
        recent = [t for t in timestamps if now - t < FAST_FAIL_WINDOW_SEC]
        self._fail_timestamps[task_id] = recent
        return len(recent) >= FAST_FAIL_THRESHOLD

    def _record_failure(self, task_id: str) -> None:
        """태스크 실패 타임스탬프 기록."""
        if task_id not in self._fail_timestamps:
            self._fail_timestamps[task_id] = []
        self._fail_timestamps[task_id].append(time.monotonic())

    @staticmethod
    def _is_token_limit_error(exc: BaseException) -> bool:
        """토큰/레이트 리밋 관련 에러인지 판별."""
        error_str = str(exc).lower()
        return any(kw in error_str for kw in TOKEN_LIMIT_KEYWORDS)

    async def _execute_task(self, task: dict) -> None:
        """태스크 콜백 실행 및 완료 후 processing set에서 제거."""
        task_id = task["id"]
        task_succeeded = False

        # ── Fast-failure 감지: 빠른 연속 실패 시 백오프 ──
        if self._is_fast_failing(task_id):
            logger.warning(
                f"[TaskPoller:{self._org_id}] 태스크 {task_id} fast-fail 감지 — "
                f"{FAST_FAIL_BACKOFF_SEC}초 백오프"
            )
            await asyncio.sleep(FAST_FAIL_BACKOFF_SEC)

        try:
            await self._on_task(task)
            task_succeeded = True
            # 성공 시 실패 이력 초기화
            self._fail_timestamps.pop(task_id, None)
        except Exception as exc:
            self._record_failure(task_id)
            if self._is_token_limit_error(exc):
                logger.error(
                    f"[TaskPoller:{self._org_id}] 태스크 {task_id} 토큰/레이트 리밋 감지 — "
                    f"{TOKEN_LIMIT_BACKOFF_SEC}초 장기 백오프 적용: {exc}"
                )
                await asyncio.sleep(TOKEN_LIMIT_BACKOFF_SEC)
            else:
                logger.exception(f"[TaskPoller:{self._org_id}] 태스크 실행 오류: {task_id}")
        finally:
            self._processing.discard(task_id)
            hb_task = self._heartbeat_tasks.pop(task_id, None)
            if hb_task and not hb_task.done():
                hb_task.cancel()
            try:
                await self._db.release_pm_task_lease(
                    task_id,
                    self._worker_id,
                    requeue_if_running=not task_succeeded,
                    **(
                        {"retry_delay_seconds": max(self._lease_ttl_sec, self._poll_interval * 4)}
                        if not task_succeeded
                        else {}
                    ),
                )
            except Exception as _rel_e:
                logger.warning(
                    f"[TaskPoller:{self._org_id}] lease release 실패 (무시): {task_id} — {_rel_e}"
                )
