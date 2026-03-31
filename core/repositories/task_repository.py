"""core.repositories.task_repository — SQLite 기반 태스크 CRUD 저장소 (Phase 2a 구현).

TaskRepositoryInterface를 구현하는 구체 클래스입니다.
aiosqlite를 사용하여 비동기 SQLite 접근을 제공합니다.

피처 플래그: ENABLE_REPOSITORY_PATTERN=1 (환경변수, 동적으로 읽음)
  - 0 (기본): 스텁 동작 (하위 호환 유지)
  - 1: 실제 SQLite DB 사용

구현 노트:
  - :memory: DB의 경우 연결별 격리 문제를 방지하기 위해 영속 연결(_conn)을 사용합니다.
  - 파일 기반 DB는 매 쿼리마다 connect()를 새로 열어도 됩니다.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import aiosqlite

# ---------------------------------------------------------------------------
# 피처 플래그 (동적 조회 — import 시점이 아닌 런타임에 읽음)
# ---------------------------------------------------------------------------


def _is_enabled(db_path: str) -> bool:
    """ENABLE_REPOSITORY_PATTERN=1 이거나 :memory: DB면 True를 반환합니다."""
    if db_path == ":memory:":
        return True
    return os.environ.get("ENABLE_REPOSITORY_PATTERN", "1") == "1"


ENABLE_REPOSITORY_PATTERN: bool = os.environ.get("ENABLE_REPOSITORY_PATTERN", "1") == "1"
"""True일 때 신규 Repository 패턴 코드 경로를 활성화합니다. (하위 호환용 상수)"""

# ---------------------------------------------------------------------------
# 기본 상수
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH: Path = Path("data/tasks.db")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT    PRIMARY KEY,
    org_id      TEXT    NOT NULL,
    description TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL,
    result      TEXT
);
"""


def _row_to_dict(row) -> dict:
    """aiosqlite Row → dict 변환."""
    return {
        "task_id": row[0],
        "org_id": row[1],
        "description": row[2],
        "status": row[3],
        "created_at": row[4],
        "updated_at": row[5],
        "result": row[6],
    }


# ---------------------------------------------------------------------------
# TaskRepository 클래스
# ---------------------------------------------------------------------------


class TaskRepository:
    """SQLite 기반 태스크 CRUD 저장소.

    TaskRepositoryInterface 프로토콜과 호환됩니다.

    :memory: DB의 경우 영속 연결(_conn)을 사용하여 테이블이 쿼리 간에 유지됩니다.
    파일 기반 DB는 쿼리마다 연결을 새로 열어 thread-safety를 보장합니다.

    사용 예시::

        repo = TaskRepository()
        await repo.initialize()
        await repo.save({"task_id": "t1", "org_id": "dev",
                         "description": "...", "status": "pending",
                         "created_at": time.time(), "updated_at": time.time()})
        task = await repo.get("t1")
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self._db_path_str = str(db_path)
        self._db_path = Path(db_path) if str(db_path) != ":memory:" else Path(":memory:")
        self._is_memory: bool = self._db_path_str == ":memory:"
        self._conn: Optional[aiosqlite.Connection] = None

    def _enabled(self) -> bool:
        return _is_enabled(self._db_path_str)

    async def _get_conn(self) -> aiosqlite.Connection:
        """:memory: DB는 영속 연결을 반환, 파일 DB는 새 연결 컨텍스트를 제공."""
        if self._is_memory:
            if self._conn is None:
                self._conn = await aiosqlite.connect(":memory:")
                self._conn.row_factory = aiosqlite.Row
            return self._conn
        raise RuntimeError("파일 DB는 _get_conn 대신 aiosqlite.connect()를 사용하세요.")

    async def initialize(self) -> None:
        """DB 파일 및 테이블을 초기화합니다 (없으면 생성).

        :memory: DB는 영속 연결에서 테이블을 생성합니다.
        파일 DB는 ENABLE_REPOSITORY_PATTERN=1 이어야 동작합니다.
        """
        if not self._enabled():
            return

        if self._is_memory:
            conn = await self._get_conn()
            await conn.execute(_CREATE_TABLE_SQL)
            await conn.commit()
        else:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self._db_path_str) as db:
                await db.execute(_CREATE_TABLE_SQL)
                await db.commit()

    async def _execute_query(self, sql: str, params: tuple = ()) -> list[dict]:
        """SELECT 쿼리를 실행하고 결과를 dict 리스트로 반환합니다."""
        if self._is_memory:
            conn = await self._get_conn()
            async with conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
            return [_row_to_dict(r) for r in rows]
        else:
            async with aiosqlite.connect(self._db_path_str) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(sql, params) as cursor:
                    rows = await cursor.fetchall()
            return [_row_to_dict(r) for r in rows]

    async def _execute_write(self, sql: str, params: tuple = ()) -> int:
        """INSERT/UPDATE/DELETE 쿼리를 실행하고 rowcount를 반환합니다."""
        if self._is_memory:
            conn = await self._get_conn()
            cursor = await conn.execute(sql, params)
            await conn.commit()
            return cursor.rowcount
        else:
            async with aiosqlite.connect(self._db_path_str) as db:
                cursor = await db.execute(sql, params)
                await db.commit()
                return cursor.rowcount

    async def get(self, task_id: str) -> dict | None:
        """task_id로 태스크를 조회합니다. 없으면 None 반환."""
        if not self._enabled():
            return None
        rows = await self._execute_query(
            "SELECT task_id, org_id, description, status, created_at, updated_at, result "
            "FROM tasks WHERE task_id = ?",
            (task_id,),
        )
        return rows[0] if rows else None

    async def save(self, task: dict) -> None:
        """태스크를 저장(INSERT OR REPLACE)합니다.

        Args:
            task: task_id, org_id, description, status, created_at, updated_at,
                  result(optional) 키를 포함하는 딕셔너리.
        """
        if not self._enabled():
            return
        now = time.time()
        await self._execute_write(
            """INSERT OR REPLACE INTO tasks
               (task_id, org_id, description, status, created_at, updated_at, result)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                task["task_id"],
                task.get("org_id", "dev"),
                task.get("description", ""),
                task.get("status", "pending"),
                task.get("created_at", now),
                task.get("updated_at", now),
                task.get("result"),
            ),
        )

    async def update_status(
        self, task_id: str, status: str, result: str | None = None
    ) -> bool:
        """태스크 상태를 업데이트합니다.

        Args:
            task_id: 업데이트할 태스크 ID.
            status: 새 상태값 (pending | in_progress | done | failed | cancelled).
            result: 옵션 결과 텍스트.

        Returns:
            True if updated, False if task_id not found.
        """
        if not self._enabled():
            return False
        now = time.time()
        rowcount = await self._execute_write(
            "UPDATE tasks SET status = ?, updated_at = ?, result = ? WHERE task_id = ?",
            (status, now, result, task_id),
        )
        return rowcount > 0

    async def list_by_status(self, status: str) -> list[dict]:
        """상태값으로 필터링된 태스크 목록을 반환합니다."""
        if not self._enabled():
            return []
        return await self._execute_query(
            "SELECT task_id, org_id, description, status, created_at, updated_at, result "
            "FROM tasks WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )

    async def list_all(self) -> list[dict]:
        """모든 태스크를 생성일 내림차순으로 반환합니다."""
        if not self._enabled():
            return []
        return await self._execute_query(
            "SELECT task_id, org_id, description, status, created_at, updated_at, result "
            "FROM tasks ORDER BY created_at DESC"
        )

    async def delete(self, task_id: str) -> None:
        """task_id에 해당하는 태스크를 삭제합니다."""
        if not self._enabled():
            return
        await self._execute_write("DELETE FROM tasks WHERE task_id = ?", (task_id,))

    async def close(self) -> None:
        """:memory: DB의 영속 연결을 닫습니다."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
