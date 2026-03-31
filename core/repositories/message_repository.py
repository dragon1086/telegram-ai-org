"""core.repositories.message_repository — 메시지 저장소 (Phase 2a 구현).

MessageRepositoryInterface를 구현하는 aiosqlite 기반 구체 클래스입니다.

테이블 스키마:
    messages(id INTEGER PK AUTOINCREMENT, task_id TEXT, content TEXT,
             sender TEXT, timestamp TEXT, created_at REAL)

참고: `:memory:` 경로 사용 시 initialize()가 반환한 연결 객체를 내부적으로 유지합니다.
      파일 경로 사용 시 각 메서드 호출마다 새 연결을 열어 자동 닫습니다.

Self-review:
  ① Logic: initialize → save → get_by_task → get_recent 전체 흐름 구현, graceful degradation 적용.
  ② Edge cases: :memory: 공유 연결 처리, 플래그 비활성화 시 no-op/빈 리스트.
  ③ Compat: 기존 인터페이스(NotImplementedError 스텁) 동일 시그니처 유지.
  ④ Global state: 없음.
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite
from loguru import logger

# ---------------------------------------------------------------------------
# 피처 플래그
# ---------------------------------------------------------------------------

ENABLE_REPOSITORY_PATTERN: bool = os.environ.get("ENABLE_REPOSITORY_PATTERN", "1") == "1"
"""True일 때 신규 Repository 패턴 코드 경로를 활성화합니다."""

# ---------------------------------------------------------------------------
# 기본 상수
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH: Path = Path("data/messages.db")

_DDL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    sender      TEXT    DEFAULT '',
    timestamp   TEXT    NOT NULL,
    created_at  REAL    NOT NULL
);
"""

_DDL_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_messages_task_id ON messages(task_id);
"""


# ---------------------------------------------------------------------------
# MessageRepository 클래스
# ---------------------------------------------------------------------------


class MessageRepository:
    """SQLite 기반 메시지 저장소.

    MessageRepositoryInterface 프로토콜과 호환됩니다.

    사용 예시::

        repo = MessageRepository()
        await repo.initialize()
        await repo.save({"task_id": "t1", "content": "...", "timestamp": "2026-03-29T00:00:00"})
        msgs = await repo.get_by_task("t1")

    `:memory:` DB 사용 시 initialize()가 내부 공유 연결을 생성하며,
    이후 모든 메서드가 동일 연결을 재사용합니다.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        # :memory: 경우 단일 연결 공유 (파일 DB는 None — 각 쿼리마다 새 연결)
        self._shared_conn: aiosqlite.Connection | None = None

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        """DB 연결 컨텍스트 매니저.

        :memory: DB는 _shared_conn을 재사용합니다.
        파일 DB는 매 호출마다 새 연결을 열어 반환합니다.
        """
        if self._shared_conn is not None:
            yield self._shared_conn
        else:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                yield db

    async def initialize(self) -> None:
        """DB 파일 및 테이블을 초기화합니다 (없으면 생성)."""
        if not ENABLE_REPOSITORY_PATTERN:
            logger.debug("MessageRepository disabled; initialize is no-op")
            return

        try:
            is_memory = str(self._db_path) == ":memory:"
            if is_memory:
                # :memory: 는 단일 연결 유지
                conn = await aiosqlite.connect(":memory:")
                conn.row_factory = aiosqlite.Row
                self._shared_conn = conn
            else:
                self._db_path.parent.mkdir(parents=True, exist_ok=True)

            async with self._connect() as db:
                await db.execute(_DDL_CREATE_TABLE)
                await db.execute(_DDL_CREATE_INDEX)
                await db.commit()
            logger.info("MessageRepository.initialize: DB 준비 완료 (%s)", self._db_path)
        except Exception as exc:
            logger.error("MessageRepository.initialize 실패: %s", exc)

    async def save(self, message: dict) -> None:
        """메시지를 저장합니다.

        Args:
            message: task_id, content, timestamp 필드 필수.
                     sender(선택, 기본 ''), created_at(선택, 기본 time.time()).
        """
        if not ENABLE_REPOSITORY_PATTERN:
            logger.debug("MessageRepository disabled; save is no-op")
            return

        try:
            task_id: str = str(message.get("task_id", ""))
            content: str = str(message.get("content", ""))
            sender: str = str(message.get("sender", ""))
            timestamp: str = str(message.get("timestamp", ""))
            created_at: float = float(message.get("created_at", time.time()))

            async with self._connect() as db:
                await db.execute(
                    "INSERT INTO messages (task_id, content, sender, timestamp, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (task_id, content, sender, timestamp, created_at),
                )
                await db.commit()
            logger.debug("MessageRepository.save: task_id=%s 저장 완료", task_id)
        except Exception as exc:
            logger.error("MessageRepository.save 실패: %s", exc)

    async def get_by_task(self, task_id: str) -> list[dict]:
        """특정 태스크에 연결된 메시지 목록을 반환합니다 (created_at ASC)."""
        if not ENABLE_REPOSITORY_PATTERN:
            logger.debug("MessageRepository disabled; get_by_task returns []")
            return []

        try:
            async with self._connect() as db:
                cursor = await db.execute(
                    "SELECT id, task_id, content, sender, timestamp, created_at"
                    " FROM messages WHERE task_id = ? ORDER BY created_at ASC",
                    (task_id,),
                )
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.error("MessageRepository.get_by_task 실패 task_id=%s: %s", task_id, exc)
            return []

    async def get_recent(self, limit: int = 100) -> list[dict]:
        """최근 메시지를 limit 개수만큼 반환합니다 (created_at DESC)."""
        if not ENABLE_REPOSITORY_PATTERN:
            logger.debug("MessageRepository disabled; get_recent returns []")
            return []

        try:
            async with self._connect() as db:
                cursor = await db.execute(
                    "SELECT id, task_id, content, sender, timestamp, created_at"
                    " FROM messages ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.error("MessageRepository.get_recent 실패: %s", exc)
            return []
