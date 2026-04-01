"""core.dashboard.adapter — 데이터 소스 어댑터 (Phase 1).

DataSourceAdapter:
    기존 태스크 시스템(YAML/SQLite DB)에서 실시간 상태를 폴링하여
    TicketStatus 목록을 반환한다.

    - 폴링 주기: 기본 5초 (DASHBOARD_POLL_INTERVAL 환경변수로 변경 가능)
    - 다중 소스 지원: YAML 파일 + SQLite DB (우선순위: DB > YAML)
    - 비동기 폴링: asyncio 기반 백그라운드 태스크

지원 데이터 소스:
    1. SQLite DB (data/tasks.db)  — TaskRepository 기반
    2. YAML 파일 (data/pm_tasks.yaml 또는 지정 경로)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Callable, Awaitable, Optional

from core.dashboard.models import TicketStatus, TicketState

logger = logging.getLogger(__name__)

# 기본 폴링 주기 (초)
DEFAULT_POLL_INTERVAL: float = float(os.environ.get("DASHBOARD_POLL_INTERVAL", "5"))

# SQLite DB 기본 경로
DEFAULT_DB_PATH: str = os.environ.get("AIMESH_DB_PATH", "data/tasks.db")

# YAML 소스 기본 경로
DEFAULT_YAML_PATH: str = os.environ.get("DASHBOARD_YAML_PATH", "data/pm_tasks.yaml")

# 상태 매핑 (기존 태스크 시스템 → TicketState)
_STATUS_MAP: dict[str, TicketState] = {
    "pending":     TicketState.PENDING,
    "in_progress": TicketState.IN_PROGRESS,
    "running":     TicketState.IN_PROGRESS,
    "done":        TicketState.DONE,
    "completed":   TicketState.DONE,
    "failed":      TicketState.BLOCKED,
    "blocked":     TicketState.BLOCKED,
    "cancelled":   TicketState.BLOCKED,
}


def _map_status(raw: str) -> TicketState:
    return _STATUS_MAP.get(str(raw).lower(), TicketState.PENDING)


# ---------------------------------------------------------------------------
# DataSourceAdapter
# ---------------------------------------------------------------------------


class DataSourceAdapter:
    """태스크 시스템에서 TicketStatus 목록을 실시간으로 폴링.

    사용 예::

        adapter = DataSourceAdapter(poll_interval=5)
        adapter.on_update(lambda tickets: print(len(tickets)))
        await adapter.start()       # 백그라운드 폴링 시작
        ...
        await adapter.stop()

    또는 단발 조회::

        tickets = await adapter.fetch_once()
    """

    def __init__(
        self,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        db_path: str = DEFAULT_DB_PATH,
        yaml_path: str = DEFAULT_YAML_PATH,
    ) -> None:
        self.poll_interval = poll_interval
        self.db_path = db_path
        self.yaml_path = yaml_path

        self._callbacks: list[Callable[[list[TicketStatus]], Awaitable[None] | None]] = []
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_tickets: list[TicketStatus] = []

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def on_update(
        self,
        callback: Callable[[list[TicketStatus]], Awaitable[None] | None],
    ) -> "DataSourceAdapter":
        """폴링 결과 수신 콜백 등록. 체이닝 가능."""
        self._callbacks.append(callback)
        return self

    async def start(self) -> None:
        """백그라운드 폴링 태스크 시작."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="dashboard-poller")
        logger.info("DataSourceAdapter 폴링 시작 (주기: %ss)", self.poll_interval)

    async def stop(self) -> None:
        """폴링 중단."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DataSourceAdapter 폴링 중단")

    async def fetch_once(self) -> list[TicketStatus]:
        """현재 시점 티켓 목록 단발 조회."""
        tickets = await self._load_from_db()
        if not tickets:
            tickets = await self._load_from_yaml()
        self._last_tickets = tickets
        return tickets

    @property
    def last_tickets(self) -> list[TicketStatus]:
        """마지막 폴링 결과 (캐시)."""
        return list(self._last_tickets)

    # ------------------------------------------------------------------
    # 내부 폴링 루프
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                tickets = await self.fetch_once()
                await self._notify(tickets)
            except Exception as exc:
                logger.warning("폴링 중 오류: %s", exc)
            await asyncio.sleep(self.poll_interval)

    async def _notify(self, tickets: list[TicketStatus]) -> None:
        for cb in self._callbacks:
            try:
                result = cb(tickets)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("콜백 오류: %s", exc)

    # ------------------------------------------------------------------
    # SQLite 소스
    # ------------------------------------------------------------------

    async def _load_from_db(self) -> list[TicketStatus]:
        """SQLite DB에서 태스크 목록을 TicketStatus 리스트로 로드."""
        try:
            import aiosqlite

            db_file = Path(self.db_path)
            if not db_file.exists() and self.db_path != ":memory:":
                return []

            async with aiosqlite.connect(str(db_file)) as conn:
                # tasks 테이블 존재 여부 확인
                async with conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
                ) as cur:
                    if not await cur.fetchone():
                        return []

                async with conn.execute(
                    "SELECT task_id, org_id, description, status, created_at, updated_at, result "
                    "FROM tasks ORDER BY updated_at DESC LIMIT 200"
                ) as cur:
                    rows = await cur.fetchall()

            tickets = []
            for row in rows:
                task_id, org_id, description, status, created_at, updated_at, result = row
                state = _map_status(status)

                # started_at / completed_at 추론
                started_at = None
                completed_at = None
                if state == TicketState.IN_PROGRESS:
                    started_at = updated_at
                elif state == TicketState.DONE:
                    completed_at = updated_at
                    started_at = created_at  # 근사값

                tickets.append(
                    TicketStatus(
                        ticket_id=task_id,
                        state=state,
                        assignee=org_id or "unassigned",
                        created_at=created_at or time.time(),
                        started_at=started_at,
                        completed_at=completed_at,
                        title=description[:80] if description else "",
                        org_id=org_id or "",
                    )
                )
            return tickets

        except ImportError:
            logger.debug("aiosqlite 미설치 — DB 소스 스킵")
            return []
        except Exception as exc:
            logger.warning("DB 로드 오류: %s", exc)
            return []

    # ------------------------------------------------------------------
    # YAML 소스 (폴백)
    # ------------------------------------------------------------------

    async def _load_from_yaml(self) -> list[TicketStatus]:
        """YAML 파일에서 태스크 목록을 TicketStatus 리스트로 로드."""
        try:
            import yaml

            yaml_file = Path(self.yaml_path)
            if not yaml_file.exists():
                return self._generate_mock_tickets()

            with yaml_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not isinstance(data, (list, dict)):
                return []

            items = data if isinstance(data, list) else data.get("tasks", [])
            tickets = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                tickets.append(
                    TicketStatus(
                        ticket_id=str(item.get("id", item.get("task_id", f"task-{id(item)}"))),
                        state=_map_status(item.get("status", "pending")),
                        assignee=str(item.get("assignee", item.get("org_id", "unassigned"))),
                        created_at=float(item.get("created_at", time.time())),
                        started_at=item.get("started_at"),
                        completed_at=item.get("completed_at"),
                        title=str(item.get("title", item.get("description", "")))[:80],
                        org_id=str(item.get("org_id", "")),
                    )
                )
            return tickets

        except Exception as exc:
            logger.warning("YAML 로드 오류: %s", exc)
            return self._generate_mock_tickets()

    # ------------------------------------------------------------------
    # 목 데이터 생성 (소스 없을 때 대시보드 시연용)
    # ------------------------------------------------------------------

    def _generate_mock_tickets(self) -> list[TicketStatus]:
        """실제 데이터 소스 없을 때 시연용 목 티켓 생성."""
        import random

        now = time.time()
        orgs = [
            "aiorg_engineering_bot",
            "aiorg_design_bot",
            "aiorg_product_bot",
            "aiorg_ops_bot",
        ]
        titles = [
            "대시보드 Phase 1 구현",
            "SSE 엔드포인트 연동",
            "TicketStatus 데이터모델 작성",
            "pytest 유닛 테스트 통과",
            "만화 캐릭터 UI 렌더링",
            "FastAPI 앱 팩토리 완성",
            "데이터 소스 어댑터 구현",
            "원격 접근 SSE 모듈",
        ]

        tickets = []
        for i, title in enumerate(titles):
            raw_state = random.choice(["pending", "in_progress", "done", "done", "in_progress"])
            created = now - random.uniform(100, 86400)
            started = created + random.uniform(10, 600) if raw_state != "pending" else None
            completed = started + random.uniform(60, 3600) if raw_state == "done" and started else None

            tickets.append(
                TicketStatus(
                    ticket_id=f"T-mock-{i+1:03d}",
                    state=_map_status(raw_state),
                    assignee=orgs[i % len(orgs)],
                    created_at=created,
                    started_at=started,
                    completed_at=completed,
                    title=title,
                    org_id=orgs[i % len(orgs)],
                )
            )
        return tickets
