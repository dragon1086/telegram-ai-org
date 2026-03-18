"""StalenessChecker — 백그라운드 asyncio 태스크로 stale 서브태스크를 자동 감지·처리."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, UTC, timedelta
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.context_db import ContextDB

STALE_THRESHOLD_SEC = float(os.environ.get("STALE_THRESHOLD_SEC", "300"))
HEARTBEAT_GRACE_SEC = float(os.environ.get("HEARTBEAT_GRACE_SEC", "120"))
SUBTASK_TIMEOUT_SEC = float(os.environ.get("SUBTASK_TIMEOUT_SEC", "600"))
CHECK_INTERVAL_SEC = float(os.environ.get("STALENESS_CHECK_INTERVAL_SEC", "60"))


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts
    except (ValueError, TypeError):
        return None


class StalenessChecker:
    """60초 주기로 DB를 스캔해 stale/timed-out 서브태스크를 자동 처리한다.

    감지 대상:
    - status == "assigned" AND created_at 경과 > STALE_THRESHOLD_SEC (300s) → 경고 로그
    - status == "assigned" AND created_at 경과 > SUBTASK_TIMEOUT_SEC (600s) → failed 처리
    - status == "running" AND lease_heartbeat_at 미갱신 > HEARTBEAT_GRACE_SEC (120s) → 경고 로그
    - status == "running" AND lease_heartbeat_at 미갱신 > HEARTBEAT_GRACE_SEC AND created_at > SUBTASK_TIMEOUT_SEC → failed 처리
    """

    def __init__(self, db: "ContextDB") -> None:
        self._db = db
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """백그라운드 asyncio task를 시작한다. 이미 실행 중이거나 이벤트 루프가 없으면 무시."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("[StalenessChecker] 실행 중인 이벤트 루프 없음, 백그라운드 루프 건너뜀")
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="staleness-checker")
            logger.info("[StalenessChecker] 백그라운드 루프 시작")

    def stop(self) -> None:
        """백그라운드 task를 취소한다."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("[StalenessChecker] 백그라운드 루프 중지")

    async def _loop(self) -> None:
        """CHECK_INTERVAL_SEC 마다 check_all()을 호출하는 루프."""
        while True:
            try:
                await asyncio.sleep(CHECK_INTERVAL_SEC)
                await self.check_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[StalenessChecker] 루프 예외 (계속 진행): {e}")

    async def check_all(self) -> None:
        """모든 active 부모 태스크의 서브태스크를 스캔한다."""
        try:
            parents = await self._db.get_active_parent_tasks()
        except Exception as e:
            logger.debug(f"[StalenessChecker] active parent 조회 실패 (무시): {e}")
            return

        for parent in parents:
            parent_id = parent.get("id") or parent.get("task_id")
            if not parent_id:
                continue
            try:
                await self.check_parent(parent_id)
            except Exception as e:
                logger.warning(f"[StalenessChecker] parent {parent_id} 체크 실패 (무시): {e}")

    async def check_parent(self, parent_id: str) -> list[str]:
        """특정 부모 태스크의 서브태스크 스탈니스/타임아웃 체크. failed 처리된 task_id 목록 반환."""
        try:
            subtasks = await self._db.get_subtasks(parent_id)
        except Exception as e:
            logger.debug(f"[StalenessChecker] get_subtasks 실패 ({parent_id}): {e}")
            return []

        now = datetime.now(UTC)
        stale_assigned_cutoff = now - timedelta(seconds=STALE_THRESHOLD_SEC)
        timeout_cutoff = now - timedelta(seconds=SUBTASK_TIMEOUT_SEC)
        heartbeat_grace_cutoff = now - timedelta(seconds=HEARTBEAT_GRACE_SEC)

        failed_ids: list[str] = []

        for st in subtasks:
            status = st.get("status", "")
            tid = st.get("id", "")
            dept = st.get("assigned_dept", "?")
            meta = st.get("metadata") or {}

            # Skip tasks with no_stale_check flag
            if meta.get("no_stale_check"):
                continue

            if status == "assigned":
                created_raw = st.get("created_at") or st.get("updated_at", "")
                ts = _parse_ts(created_raw)
                if ts and ts < stale_assigned_cutoff:
                    elapsed = int((now - ts).total_seconds())
                    if ts < timeout_cutoff:
                        logger.warning(
                            f"[StalenessChecker] TIMEOUT assigned→failed: {tid} "
                            f"(dept={dept}, {elapsed}s elapsed)"
                        )
                        await self._fail_subtask(tid, "assigned 타임아웃 ({elapsed}s)")
                        failed_ids.append(tid)
                    else:
                        logger.warning(
                            f"[StalenessChecker] STALE assigned: {tid} "
                            f"(dept={dept}, {elapsed}s elapsed)"
                        )

            elif status == "running":
                # heartbeat은 metadata['lease_heartbeat_at']에 저장됨
                heartbeat_raw = meta.get("lease_heartbeat_at") or st.get("updated_at", "")
                hb_ts = _parse_ts(heartbeat_raw)
                if hb_ts and hb_ts < heartbeat_grace_cutoff:
                    elapsed_hb = int((now - hb_ts).total_seconds())
                    created_raw = st.get("created_at", "")
                    created_ts = _parse_ts(created_raw)
                    if created_ts and created_ts < timeout_cutoff:
                        logger.warning(
                            f"[StalenessChecker] TIMEOUT running→failed: {tid} "
                            f"(dept={dept}, heartbeat {elapsed_hb}s ago)"
                        )
                        await self._fail_subtask(tid, f"heartbeat 타임아웃 ({elapsed_hb}s)")
                        failed_ids.append(tid)
                    else:
                        logger.warning(
                            f"[StalenessChecker] HEARTBEAT 미갱신 경고: {tid} "
                            f"(dept={dept}, {elapsed_hb}s ago)"
                        )

        return failed_ids

    async def _fail_subtask(self, task_id: str, reason: str) -> None:
        """서브태스크를 failed 처리한다."""
        try:
            await self._db.update_pm_task_status(
                task_id, "failed", result=f"[StalenessChecker] {reason}"
            )
            logger.info(f"[StalenessChecker] {task_id} → failed ({reason})")
        except Exception as e:
            logger.warning(f"[StalenessChecker] fail 처리 실패 ({task_id}): {e}")
