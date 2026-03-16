"""워커 상태 모니터링 — usefulness 기반 헬스체크 + 리트라이/DLQ 관리."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class WorkerStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    DEGRADED = "degraded"          # 연속 실패 3회 초과 — 태스크 수락 가능하나 후순위
    QUARANTINED = "quarantined"    # 연속 실패 5회 초과 — 수동 리셋 전까지 태스크 차단
    OFFLINE = "offline"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class WorkerHealth:
    """개별 워커의 상태 + 성과 지표."""

    name: str
    status: WorkerStatus = WorkerStatus.UNKNOWN
    last_seen: float = field(default_factory=time.time)
    current_task: str | None = None

    # --- 기존 호환 필드 ---
    completed_tasks: int = 0
    failed_tasks: int = 0

    # --- usefulness 지표 ---
    success_count: int = 0
    fail_count: int = 0
    consecutive_failures: int = 0

    # --- 리스 시스템 ---
    last_active_ts: float = field(default_factory=time.time)
    lease_expires_at: float = 0.0  # 0이면 리스 미설정

    # --- 레이턴시 추적 ---
    _task_start_ts: float = 0.0
    _total_latency: float = 0.0
    _latency_count: int = 0

    @property
    def success_rate(self) -> float:
        """성공률 (0.0 ~ 1.0). 처리 건수 0이면 1.0 반환."""
        total = self.success_count + self.fail_count
        if total == 0:
            return 1.0
        return self.success_count / total

    @property
    def avg_latency(self) -> float:
        """평균 태스크 처리 시간 (초)."""
        if self._latency_count == 0:
            return 0.0
        return self._total_latency / self._latency_count

    @property
    def is_available(self) -> bool:
        """ONLINE 또는 UNKNOWN이면 태스크 수락 가능."""
        return self.status in (WorkerStatus.ONLINE, WorkerStatus.UNKNOWN)

    @property
    def is_assignable(self) -> bool:
        """태스크 할당 가능 여부 — DEGRADED도 포함 (후순위)."""
        return self.status in (
            WorkerStatus.ONLINE,
            WorkerStatus.UNKNOWN,
            WorkerStatus.DEGRADED,
        )

    @property
    def last_seen_ago(self) -> float:
        return time.time() - self.last_seen


@dataclass
class DLQEntry:
    """Dead-Letter Queue 항목."""

    task_id: str
    worker_name: str
    reason: str
    attempts: int
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# 메인 모니터
# ---------------------------------------------------------------------------

class WorkerHealthMonitor:
    """워커 상태를 추적하고 PM에게 가용 워커 목록 제공.

    기존 공개 API 100% 하위호환 + usefulness 기반 확장.
    """

    OFFLINE_THRESHOLD = 300          # 5분 무응답 → 오프라인
    LEASE_DURATION = 120             # 리스 기본 유효기간 (초)
    DEGRADED_THRESHOLD = 3           # 연속 실패 → DEGRADED
    QUARANTINE_THRESHOLD = 5         # 연속 실패 → QUARANTINED

    # 리트라이 백오프 설정
    RETRY_BASE_DELAY = 2.0           # 초
    RETRY_MAX_DELAY = 120.0          # 초
    DEFAULT_MAX_ATTEMPTS = 3
    DLQ_MAX_SIZE = 100               # DLQ 최대 크기 (초과 시 FIFO 방식 제거)

    def __init__(self) -> None:
        self._health: dict[str, WorkerHealth] = {}
        self._attempts: dict[str, int] = {}        # task_id → 시도 횟수
        self._dlq: list[DLQEntry] = []              # Dead-Letter Queue

        # 전체 지표
        self._total_processed: int = 0
        self._total_failed: int = 0

    # -----------------------------------------------------------------------
    # 기존 공개 API (하위호환)
    # -----------------------------------------------------------------------

    def register(self, name: str) -> None:
        if name not in self._health:
            self._health[name] = WorkerHealth(name=name)
            logger.info(f"워커 등록: {name}")

    def mark_online(self, name: str) -> None:
        self._ensure(name)
        h = self._health[name]
        h.status = WorkerStatus.ONLINE
        h.last_seen = time.time()
        h.last_active_ts = h.last_seen
        h.lease_expires_at = h.last_seen + self.LEASE_DURATION

    def mark_busy(self, name: str, task_id: str) -> None:
        self._ensure(name)
        h = self._health[name]
        h.status = WorkerStatus.BUSY
        h.current_task = task_id
        h.last_seen = time.time()
        h.last_active_ts = h.last_seen
        h.lease_expires_at = h.last_seen + self.LEASE_DURATION
        h._task_start_ts = h.last_seen

    def mark_done(self, name: str, success: bool = True) -> None:
        self._ensure(name)
        h = self._health[name]
        now = time.time()

        # 레이턴시 기록
        if h._task_start_ts > 0:
            latency = now - h._task_start_ts
            h._total_latency += latency
            h._latency_count += 1
            h._task_start_ts = 0.0

        h.current_task = None
        h.last_seen = now
        h.last_active_ts = now
        h.lease_expires_at = now + self.LEASE_DURATION
        self._total_processed += 1

        if success:
            h.completed_tasks += 1
            h.success_count += 1
            h.consecutive_failures = 0
            h.status = WorkerStatus.ONLINE
        else:
            h.failed_tasks += 1
            h.fail_count += 1
            h.consecutive_failures += 1
            self._total_failed += 1

            # 연속 실패에 따른 상태 전환
            if h.consecutive_failures > self.QUARANTINE_THRESHOLD:
                h.status = WorkerStatus.QUARANTINED
                logger.error(
                    f"워커 격리 (연속 실패 {h.consecutive_failures}회): {name}"
                )
            elif h.consecutive_failures > self.DEGRADED_THRESHOLD:
                h.status = WorkerStatus.DEGRADED
                logger.warning(
                    f"워커 성능 저하 (연속 실패 {h.consecutive_failures}회): {name}"
                )
            else:
                h.status = WorkerStatus.ONLINE

    def mark_offline(self, name: str) -> None:
        self._ensure(name)
        self._health[name].status = WorkerStatus.OFFLINE

    def get_available(self) -> list[str]:
        """현재 태스크 받을 수 있는 워커 목록.

        ONLINE/UNKNOWN 워커 우선, DEGRADED 워커는 뒤에 배치.
        리스 만료 → DEGRADED → OFFLINE 순으로 자동 강등.
        """
        now = time.time()
        primary: list[str] = []
        degraded: list[str] = []

        for name, h in self._health.items():
            if h.status == WorkerStatus.QUARANTINED:
                continue

            # 리스 만료 체크
            if (
                h.lease_expires_at > 0
                and now > h.lease_expires_at
                and h.status not in (WorkerStatus.OFFLINE, WorkerStatus.QUARANTINED)
            ):
                if h.status == WorkerStatus.DEGRADED:
                    # 이미 DEGRADED인데 리스 만료 → OFFLINE
                    h.status = WorkerStatus.OFFLINE
                    logger.warning(f"워커 오프라인 (리스 만료): {name}")
                    continue
                else:
                    h.status = WorkerStatus.DEGRADED
                    logger.warning(f"워커 성능 저하 (리스 만료): {name}")

            # 기존 OFFLINE_THRESHOLD 체크 (하위호환)
            if h.status not in (WorkerStatus.OFFLINE, WorkerStatus.DEGRADED) and h.last_seen_ago > self.OFFLINE_THRESHOLD:
                h.status = WorkerStatus.OFFLINE
                logger.warning(f"워커 오프라인 (응답 없음): {name}")

            if h.is_available:
                primary.append(name)
            elif h.status == WorkerStatus.DEGRADED:
                degraded.append(name)

        # ONLINE 우선, DEGRADED 후순위
        return primary + degraded

    def get_status_report(self) -> str:
        """PM이 그룹 채팅에 올릴 상태 보고."""
        status_icons = {
            "online": "🟢",
            "busy": "🟡",
            "degraded": "🟠",
            "quarantined": "🔴",
            "offline": "🔴",
            "unknown": "⚪",
        }
        lines = ["📊 **워커 상태**"]
        for name, h in self._health.items():
            icon = status_icons.get(h.status.value, "⚪")
            task_info = f" → {h.current_task}" if h.current_task else ""
            rate = f"{h.success_rate:.0%}" if (h.success_count + h.fail_count) > 0 else "-"
            stats = f"(완료:{h.completed_tasks} 실패:{h.failed_tasks} 성공률:{rate})"
            lines.append(f"{icon} {name}{task_info} {stats}")
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # 리스 갱신
    # -----------------------------------------------------------------------

    def renew_lease(self, name: str, duration: float | None = None) -> None:
        """워커 리스 갱신. heartbeat 대용으로 호출."""
        self._ensure(name)
        h = self._health[name]
        now = time.time()
        h.last_active_ts = now
        h.last_seen = now
        h.lease_expires_at = now + (duration or self.LEASE_DURATION)

    # -----------------------------------------------------------------------
    # 격리 해제
    # -----------------------------------------------------------------------

    def reset_worker(self, name: str) -> None:
        """QUARANTINED/DEGRADED 워커를 수동 리셋하여 ONLINE 복귀."""
        self._ensure(name)
        h = self._health[name]
        h.consecutive_failures = 0
        h.status = WorkerStatus.ONLINE
        h.last_seen = time.time()
        h.last_active_ts = h.last_seen
        h.lease_expires_at = h.last_seen + self.LEASE_DURATION
        logger.info(f"워커 수동 리셋: {name}")

    # -----------------------------------------------------------------------
    # 리트라이 / 시도 추적
    # -----------------------------------------------------------------------

    def record_attempt(self, task_id: str) -> int:
        """태스크 시도 횟수 증가. 현재 시도 횟수 반환."""
        self._attempts[task_id] = self._attempts.get(task_id, 0) + 1
        return self._attempts[task_id]

    def get_attempt_count(self, task_id: str) -> int:
        """현재까지 시도 횟수."""
        return self._attempts.get(task_id, 0)

    def should_retry(self, task_id: str, max_attempts: int | None = None) -> bool:
        """최대 시도 횟수 미만이면 True."""
        limit = max_attempts if max_attempts is not None else self.DEFAULT_MAX_ATTEMPTS
        return self._attempts.get(task_id, 0) < limit

    def get_retry_delay(self, task_id: str) -> float:
        """지수 백오프 딜레이 (초). base=2s, max=120s."""
        attempts = self._attempts.get(task_id, 0)
        if attempts <= 0:
            return 0.0
        delay = self.RETRY_BASE_DELAY * (2 ** (attempts - 1))
        return min(delay, self.RETRY_MAX_DELAY)

    # -----------------------------------------------------------------------
    # Dead-Letter Queue
    # -----------------------------------------------------------------------

    def move_to_dlq(self, task_id: str, worker_name: str, reason: str) -> None:
        """최대 시도 초과 태스크를 DLQ로 이동."""
        entry = DLQEntry(
            task_id=task_id,
            worker_name=worker_name,
            reason=reason,
            attempts=self._attempts.get(task_id, 0),
        )
        if len(self._dlq) >= self.DLQ_MAX_SIZE:
            evicted = self._dlq.pop(0)
            logger.warning(f"DLQ 가득 참 (max={self.DLQ_MAX_SIZE}), 오래된 항목 제거: task={evicted.task_id}")
        self._dlq.append(entry)
        # 시도 카운터 정리
        self._attempts.pop(task_id, None)
        logger.warning(f"DLQ 이동: task={task_id} worker={worker_name} reason={reason}")

    def get_dlq(self) -> list[DLQEntry]:
        """DLQ 항목 목록 반환 (복사본)."""
        return list(self._dlq)

    @property
    def dlq_size(self) -> int:
        return len(self._dlq)

    # -----------------------------------------------------------------------
    # 메트릭스
    # -----------------------------------------------------------------------

    def get_metrics(self) -> dict:
        """전체 시스템 지표."""
        workers_online = 0
        workers_degraded = 0
        workers_quarantined = 0
        total_latency = 0.0
        latency_count = 0

        for h in self._health.values():
            if h.status in (WorkerStatus.ONLINE, WorkerStatus.BUSY, WorkerStatus.UNKNOWN):
                workers_online += 1
            elif h.status == WorkerStatus.DEGRADED:
                workers_degraded += 1
            elif h.status == WorkerStatus.QUARANTINED:
                workers_quarantined += 1

            total_latency += h._total_latency
            latency_count += h._latency_count

        avg_latency = total_latency / latency_count if latency_count > 0 else 0.0

        return {
            "total_processed": self._total_processed,
            "total_failed": self._total_failed,
            "avg_latency_sec": round(avg_latency, 3),
            "dlq_size": self.dlq_size,
            "workers_online": workers_online,
            "workers_degraded": workers_degraded,
            "workers_quarantined": workers_quarantined,
        }

    # -----------------------------------------------------------------------
    # 내부 헬퍼
    # -----------------------------------------------------------------------

    def _ensure(self, name: str) -> None:
        if name not in self._health:
            self.register(name)

    async def heartbeat_loop(self, interval: int = 60) -> None:
        """주기적으로 리스 만료 / 오프라인 체크."""
        while True:
            await asyncio.sleep(interval)
            self.get_available()  # 리스 만료 + 오프라인 체크 트리거
