"""core.repositories.bot_state_repository — 봇 상태 저장소 (Phase 2a 구현).

BotStateRepositoryInterface를 구현하는 aiosqlite 기반 구체 클래스입니다.

테이블 스키마:
    bot_states(bot_id TEXT PK, state TEXT JSON, is_alive INTEGER, updated_at REAL)

Self-review:
  ① Logic: initialize → update_state → get_state → get_all_alive → mark_dead 전체 흐름 구현.
     :memory: DB는 단일 공유 연결, 파일 DB는 쿼리마다 새 연결 — MessageRepository와 동일 패턴.
  ② Edge cases: 플래그 비활성화 시 no-op/None/빈 리스트, DB 오류 graceful degradation.
  ③ Compat: NotImplementedError 스텁을 실제 구현으로 교체 — 공개 시그니처 동일.
  ④ Global state: 없음.
"""
from __future__ import annotations

import json
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

DEFAULT_DB_PATH: Path = Path("data/bot_states.db")

_DDL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS bot_states (
    bot_id     TEXT    PRIMARY KEY,
    state      TEXT    NOT NULL DEFAULT '{}',
    is_alive   INTEGER NOT NULL DEFAULT 1,
    updated_at REAL    NOT NULL
);
"""


# ---------------------------------------------------------------------------
# BotStateRepository 클래스
# ---------------------------------------------------------------------------


class BotStateRepository:
    """SQLite 기반 봇 상태 저장소.

    BotStateRepositoryInterface 프로토콜과 호환됩니다.

    사용 예시::

        repo = BotStateRepository()
        await repo.initialize()
        await repo.update_state("dev_bot", {"is_alive": True, "last_seen": "2026-03-31T09:00:00"})
        alive = await repo.get_all_alive()

    `:memory:` DB 사용 시 initialize()가 내부 공유 연결을 생성하며,
    이후 모든 메서드가 동일 연결을 재사용합니다.

    Args:
        db_path: SQLite DB 파일 경로 또는 ":memory:".
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
        """DB 파일 및 테이블을 초기화합니다 (없으면 생성).

        Returns:
            None

        Raises:
            (내부적으로 catch — 오류 시 logger.error 출력 후 반환)
        """
        if not ENABLE_REPOSITORY_PATTERN:
            logger.debug("BotStateRepository disabled; initialize is no-op")
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
                await db.commit()
            logger.info("BotStateRepository.initialize: DB 준비 완료 (%s)", self._db_path)
        except Exception as exc:
            logger.error("BotStateRepository.initialize 실패: %s", exc)

    async def get_state(self, bot_id: str) -> dict | None:
        """bot_id의 현재 상태를 반환합니다.

        Args:
            bot_id: 봇 식별자 (예: "aiorg_engineering_bot").

        Returns:
            {bot_id, state: dict, is_alive: bool, updated_at: float} 또는 None(없으면).

        Raises:
            (내부적으로 catch)
        """
        if not ENABLE_REPOSITORY_PATTERN:
            logger.debug("BotStateRepository disabled; get_state returns None")
            return None

        try:
            async with self._connect() as db:
                cursor = await db.execute(
                    "SELECT bot_id, state, is_alive, updated_at"
                    " FROM bot_states WHERE bot_id = ?",
                    (bot_id,),
                )
                row = await cursor.fetchone()
            if row is None:
                return None
            result = dict(row)
            result["state"] = json.loads(result.get("state") or "{}")
            result["is_alive"] = bool(result["is_alive"])
            return result
        except Exception as exc:
            logger.error("BotStateRepository.get_state 실패 bot_id=%s: %s", bot_id, exc)
            return None

    async def update_state(self, bot_id: str, state: dict) -> None:
        """bot_id의 상태를 갱신합니다 (없으면 INSERT, 있으면 UPDATE).

        Args:
            bot_id: 봇 식별자.
            state: 상태 딕셔너리. "is_alive" 키가 있으면 해당 컬럼에도 반영.

        Returns:
            None

        Raises:
            (내부적으로 catch)
        """
        if not ENABLE_REPOSITORY_PATTERN:
            logger.debug("BotStateRepository disabled; update_state is no-op")
            return

        try:
            state_json = json.dumps(state, ensure_ascii=False)
            is_alive = int(bool(state.get("is_alive", True)))
            now = time.time()

            async with self._connect() as db:
                await db.execute(
                    """
                    INSERT INTO bot_states (bot_id, state, is_alive, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(bot_id) DO UPDATE SET
                        state      = excluded.state,
                        is_alive   = excluded.is_alive,
                        updated_at = excluded.updated_at
                    """,
                    (bot_id, state_json, is_alive, now),
                )
                await db.commit()
            logger.debug("BotStateRepository.update_state: bot_id=%s 갱신 완료", bot_id)
        except Exception as exc:
            logger.error("BotStateRepository.update_state 실패 bot_id=%s: %s", bot_id, exc)

    async def get_all_alive(self) -> list[dict]:
        """is_alive=True인 모든 봇 상태 목록을 반환합니다.

        Returns:
            [{bot_id, state, is_alive, updated_at}, ...] 목록.
            플래그 비활성화 또는 오류 시 빈 리스트.

        Raises:
            (내부적으로 catch)
        """
        if not ENABLE_REPOSITORY_PATTERN:
            logger.debug("BotStateRepository disabled; get_all_alive returns []")
            return []

        try:
            async with self._connect() as db:
                cursor = await db.execute(
                    "SELECT bot_id, state, is_alive, updated_at"
                    " FROM bot_states WHERE is_alive = 1"
                    " ORDER BY updated_at DESC",
                )
                rows = await cursor.fetchall()
            result = []
            for row in rows:
                r = dict(row)
                r["state"] = json.loads(r.get("state") or "{}")
                r["is_alive"] = bool(r["is_alive"])
                result.append(r)
            return result
        except Exception as exc:
            logger.error("BotStateRepository.get_all_alive 실패: %s", exc)
            return []

    async def mark_dead(self, bot_id: str) -> None:
        """bot_id의 is_alive를 False로 설정합니다.

        Args:
            bot_id: 봇 식별자.

        Returns:
            None

        Raises:
            (내부적으로 catch)
        """
        if not ENABLE_REPOSITORY_PATTERN:
            logger.debug("BotStateRepository disabled; mark_dead is no-op")
            return

        try:
            now = time.time()
            async with self._connect() as db:
                await db.execute(
                    "UPDATE bot_states SET is_alive = 0, updated_at = ? WHERE bot_id = ?",
                    (now, bot_id),
                )
                await db.commit()
            logger.debug("BotStateRepository.mark_dead: bot_id=%s → is_alive=False", bot_id)
        except Exception as exc:
            logger.error("BotStateRepository.mark_dead 실패 bot_id=%s: %s", bot_id, exc)
