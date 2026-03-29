"""core.repositories.message_repository — 메시지 저장소 (Phase 2a 스캐폴딩).

MessageRepositoryInterface를 구현하는 구체 클래스입니다.
실제 DB 로직은 Phase 2a 구현 시 채워집니다.
"""
from __future__ import annotations

import os
from pathlib import Path

import aiosqlite  # noqa: F401 — 의존성 존재 확인용

# ---------------------------------------------------------------------------
# 피처 플래그
# ---------------------------------------------------------------------------

ENABLE_REPOSITORY_PATTERN: bool = os.environ.get("ENABLE_REPOSITORY_PATTERN", "0") == "1"
"""True일 때 신규 Repository 패턴 코드 경로를 활성화합니다."""

# ---------------------------------------------------------------------------
# 기본 상수
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH: Path = Path("data/messages.db")


# ---------------------------------------------------------------------------
# MessageRepository 클래스
# ---------------------------------------------------------------------------


class MessageRepository:
    """SQLite 기반 메시지 저장소.

    MessageRepositoryInterface 프로토콜과 호환됩니다.

    사용 예시::

        repo = MessageRepository()
        await repo.save({"task_id": "t1", "content": "...", "timestamp": "..."})
        msgs = await repo.get_by_task("t1")
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)

    async def initialize(self) -> None:
        """DB 파일 및 테이블을 초기화합니다 (없으면 생성)."""
        # TODO(Phase 2a): CREATE TABLE messages IF NOT EXISTS 구현
        raise NotImplementedError("MessageRepository.initialize — Phase 2a 구현 예정")

    async def save(self, message: dict) -> None:
        """메시지를 저장합니다."""
        # TODO(Phase 2a): INSERT INTO messages 구현
        raise NotImplementedError("MessageRepository.save — Phase 2a 구현 예정")

    async def get_by_task(self, task_id: str) -> list[dict]:
        """특정 태스크에 연결된 메시지 목록을 반환합니다."""
        # TODO(Phase 2a): SELECT * FROM messages WHERE task_id = ? 구현
        raise NotImplementedError("MessageRepository.get_by_task — Phase 2a 구현 예정")

    async def get_recent(self, limit: int = 100) -> list[dict]:
        """최근 메시지를 limit 개수만큼 반환합니다."""
        # TODO(Phase 2a): SELECT * FROM messages ORDER BY timestamp DESC LIMIT ? 구현
        raise NotImplementedError("MessageRepository.get_recent — Phase 2a 구현 예정")
