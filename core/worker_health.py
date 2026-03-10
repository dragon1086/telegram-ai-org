"""워커 상태 모니터링 — PM이 온라인 워커만 태스크 할당."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class WorkerStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class WorkerHealth:
    name: str
    status: WorkerStatus = WorkerStatus.UNKNOWN
    last_seen: float = field(default_factory=time.time)
    current_task: str | None = None
    completed_tasks: int = 0
    failed_tasks: int = 0

    @property
    def is_available(self) -> bool:
        return self.status in (WorkerStatus.ONLINE, WorkerStatus.UNKNOWN)

    @property
    def last_seen_ago(self) -> float:
        return time.time() - self.last_seen


class WorkerHealthMonitor:
    """워커 상태를 추적하고 PM에게 가용 워커 목록 제공."""

    OFFLINE_THRESHOLD = 300  # 5분 응답 없으면 오프라인으로 간주

    def __init__(self) -> None:
        self._health: dict[str, WorkerHealth] = {}

    def register(self, name: str) -> None:
        if name not in self._health:
            self._health[name] = WorkerHealth(name=name)
            logger.info(f"워커 등록: {name}")

    def mark_online(self, name: str) -> None:
        self._ensure(name)
        self._health[name].status = WorkerStatus.ONLINE
        self._health[name].last_seen = time.time()

    def mark_busy(self, name: str, task_id: str) -> None:
        self._ensure(name)
        self._health[name].status = WorkerStatus.BUSY
        self._health[name].current_task = task_id
        self._health[name].last_seen = time.time()

    def mark_done(self, name: str, success: bool = True) -> None:
        self._ensure(name)
        h = self._health[name]
        h.status = WorkerStatus.ONLINE
        h.current_task = None
        h.last_seen = time.time()
        if success:
            h.completed_tasks += 1
        else:
            h.failed_tasks += 1

    def mark_offline(self, name: str) -> None:
        self._ensure(name)
        self._health[name].status = WorkerStatus.OFFLINE

    def get_available(self) -> list[str]:
        """현재 태스크 받을 수 있는 워커 목록."""
        available = []
        for name, h in self._health.items():
            # 오래된 워커는 오프라인 처리
            if h.status != WorkerStatus.OFFLINE and h.last_seen_ago > self.OFFLINE_THRESHOLD:
                h.status = WorkerStatus.OFFLINE
                logger.warning(f"워커 오프라인 (응답 없음): {name}")
            if h.is_available:
                available.append(name)
        return available

    def get_status_report(self) -> str:
        """PM이 그룹 채팅에 올릴 상태 보고."""
        lines = ["📊 **워커 상태**"]
        for name, h in self._health.items():
            icon = {"online": "🟢", "busy": "🟡", "offline": "🔴", "unknown": "⚪"}.get(h.status, "⚪")
            task_info = f" → {h.current_task}" if h.current_task else ""
            stats = f"(완료:{h.completed_tasks} 실패:{h.failed_tasks})"
            lines.append(f"{icon} {name}{task_info} {stats}")
        return "\n".join(lines)

    def _ensure(self, name: str) -> None:
        if name not in self._health:
            self.register(name)

    async def heartbeat_loop(self, interval: int = 60) -> None:
        """주기적으로 오래된 워커 상태 갱신."""
        while True:
            await asyncio.sleep(interval)
            self.get_available()  # 오프라인 체크 트리거
