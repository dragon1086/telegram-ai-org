"""StalenessChecker — 백그라운드 asyncio 태스크로 stale 서브태스크를 자동 감지·처리."""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.context_db import ContextDB

STALE_THRESHOLD_SEC = float(os.environ.get("STALE_THRESHOLD_SEC", "300"))
HEARTBEAT_GRACE_SEC = float(os.environ.get("HEARTBEAT_GRACE_SEC", "120"))
SUBTASK_TIMEOUT_SEC = float(os.environ.get("SUBTASK_TIMEOUT_SEC", "600"))
CHECK_INTERVAL_SEC = float(os.environ.get("STALENESS_CHECK_INTERVAL_SEC", "60"))
MAX_TIMEOUT_RETRIES = int(os.environ.get("MAX_TIMEOUT_RETRIES", "2"))


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
                        await self._fail_subtask(st, "assigned 타임아웃 ({elapsed}s)")
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
                    # heartbeat 기준으로 타임아웃 판단 (created_at 기준 제거 — 장시간 작업 오탐 방지)
                    if hb_ts < timeout_cutoff:
                        logger.warning(
                            f"[StalenessChecker] TIMEOUT running→failed: {tid} "
                            f"(dept={dept}, heartbeat {elapsed_hb}s ago)"
                        )
                        await self._fail_subtask(st, f"heartbeat 타임아웃 ({elapsed_hb}s)")
                        failed_ids.append(tid)
                    else:
                        logger.warning(
                            f"[StalenessChecker] HEARTBEAT 미갱신 경고: {tid} "
                            f"(dept={dept}, {elapsed_hb}s ago)"
                        )

        return failed_ids

    async def _fail_subtask(self, subtask: dict, reason: str) -> None:
        """서브태스크를 failed 처리하고, 후속 보완 태스크를 자동 생성한다.

        타임아웃으로 실패한 태스크는 단순히 failed로 끝내지 않고,
        같은 부서에 후속 태스크를 생성하여 작업이 완료될 때까지 추적한다.
        MAX_TIMEOUT_RETRIES 횟수를 초과하면 더 이상 후속 태스크를 만들지 않는다.
        """
        task_id = subtask.get("id", "")
        try:
            await self._db.update_pm_task_status(
                task_id, "failed", result=f"[StalenessChecker] {reason}"
            )
            logger.info(f"[StalenessChecker] {task_id} → failed ({reason})")
        except Exception as e:
            logger.warning(f"[StalenessChecker] fail 처리 실패 ({task_id}): {e}")
            return

        # 후속 보완 태스크 생성
        await self._create_followup_task(subtask, reason)

    async def _create_followup_task(self, failed_subtask: dict, reason: str) -> None:
        """타임아웃된 서브태스크의 후속 보완 태스크를 생성한다."""
        task_id = failed_subtask.get("id", "")
        parent_id = failed_subtask.get("parent_id")
        dept = failed_subtask.get("assigned_dept", "")
        description = failed_subtask.get("description", "")
        meta = failed_subtask.get("metadata") or {}

        if not parent_id or not dept:
            logger.debug(f"[StalenessChecker] 후속 태스크 생성 불가 (parent/dept 없음): {task_id}")
            return

        # 재시도 횟수 체크 — 무한 루프 방지
        retry_count = int(meta.get("timeout_retry_count", 0))
        if retry_count >= MAX_TIMEOUT_RETRIES:
            logger.warning(
                f"[StalenessChecker] 최대 재시도 초과 ({retry_count}/{MAX_TIMEOUT_RETRIES}), "
                f"후속 태스크 미생성: {task_id}"
            )
            return

        # 고유 후속 태스크 ID 생성
        now = datetime.now(UTC)
        ts_suffix = now.strftime("%H%M%S")
        followup_id = f"{task_id}-retry{retry_count + 1}-{ts_suffix}"

        followup_desc = (
            f"[타임아웃 후속] 이전 태스크 {task_id}가 타임아웃으로 실패함 ({reason}). "
            f"원래 작업을 이어서 완료하라. 원래 작업 내용: {description[:300]}"
        )
        followup_meta = {
            "retry_of": task_id,
            "timeout_retry_count": retry_count + 1,
            "original_description": description[:500],
        }

        try:
            await self._db.create_pm_task(
                task_id=followup_id,
                description=followup_desc,
                assigned_dept=dept,
                created_by="staleness_checker",
                parent_id=parent_id,
                metadata=followup_meta,
            )
            logger.info(
                f"[StalenessChecker] 후속 태스크 생성: {followup_id} "
                f"(dept={dept}, retry {retry_count + 1}/{MAX_TIMEOUT_RETRIES})"
            )
        except Exception as e:
            logger.warning(f"[StalenessChecker] 후속 태스크 생성 실패 ({followup_id}): {e}")
