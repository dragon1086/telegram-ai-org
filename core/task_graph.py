"""태스크 의존성 DAG — ContextDB 기반 크로스 프로세스 공유."""
from __future__ import annotations

from loguru import logger

from core.context_db import ContextDB


class TaskGraph:
    """ContextDB pm_task_dependencies 테이블 기반 태스크 의존성 그래프."""

    def __init__(self, context_db: ContextDB):
        self._db = context_db

    async def add_task(self, task_id: str, depends_on: list[str] | None = None) -> None:
        """태스크를 그래프에 추가하고 의존성 기록. 순환 감지 시 ValueError."""
        deps = depends_on or []
        if deps and await self.detect_cycle(task_id, deps):
            raise ValueError(f"순환 의존성 감지: {task_id} -> {deps}")
        for dep_id in deps:
            await self._db.add_dependency(task_id, dep_id)
        logger.debug(f"TaskGraph: {task_id} 추가 (deps={deps})")

    async def get_ready_tasks(self, parent_id: str) -> list[str]:
        """의존성이 모두 완료된 실행 가능 태스크 ID 목록."""
        ready = await self._db.get_ready_tasks(parent_id)
        return [t["id"] for t in ready]

    async def mark_complete(self, task_id: str) -> list[str]:
        """태스크 완료 처리. 새로 unblock된 태스크 ID 목록 반환."""
        task = await self._db.get_pm_task(task_id)
        if not task:
            return []
        parent_id = task.get("parent_id")
        # 완료 전 ready 목록
        before = set(await self.get_ready_tasks(parent_id)) if parent_id else set()
        await self._db.update_pm_task_status(task_id, "done")
        # 완료 후 ready 목록
        after = set(await self.get_ready_tasks(parent_id)) if parent_id else set()
        newly_ready = list(after - before)
        if newly_ready:
            logger.info(f"TaskGraph: {task_id} 완료 → 새로 실행 가능: {newly_ready}")
        return newly_ready

    async def detect_cycle(self, task_id: str, depends_on: list[str]) -> bool:
        """의존성 추가 시 순환이 생기는지 DFS로 검사."""
        # task_id가 depends_on의 조상(직/간접 의존 대상)이면 순환
        visited: set[str] = set()

        async def _has_path(from_id: str, to_id: str) -> bool:
            """from_id에서 to_id로 가는 경로가 있는지 (ContextDB 조회)."""
            if from_id == to_id:
                return True
            if from_id in visited:
                return False
            visited.add(from_id)
            # from_id가 의존하는 태스크들 조회
            import aiosqlite
            async with aiosqlite.connect(self._db.db_path) as db:
                cursor = await db.execute(
                    "SELECT depends_on FROM pm_task_dependencies WHERE task_id=?",
                    (from_id,),
                )
                rows = await cursor.fetchall()
            for row in rows:
                if await _has_path(row[0], to_id):
                    return True
            return False

        for dep in depends_on:
            visited.clear()
            if await _has_path(dep, task_id):
                return True
        return False
