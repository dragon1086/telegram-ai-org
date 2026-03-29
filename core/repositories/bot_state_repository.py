"""core.repositories.bot_state_repository — 봇 상태 저장소 (Phase 2a 스캐폴딩).

BotStateRepositoryInterface를 구현하는 구체 클래스입니다.
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

DEFAULT_DB_PATH: Path = Path("data/bot_states.db")


# ---------------------------------------------------------------------------
# BotStateRepository 클래스
# ---------------------------------------------------------------------------


class BotStateRepository:
    """SQLite 기반 봇 상태 저장소.

    BotStateRepositoryInterface 프로토콜과 호환됩니다.

    사용 예시::

        repo = BotStateRepository()
        await repo.update_state("dev_bot", {"is_alive": True, "last_seen": "..."})
        alive = await repo.get_all_alive()
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)

    async def initialize(self) -> None:
        """DB 파일 및 테이블을 초기화합니다 (없으면 생성)."""
        # TODO(Phase 2a): CREATE TABLE bot_states IF NOT EXISTS 구현
        raise NotImplementedError("BotStateRepository.initialize — Phase 2a 구현 예정")

    async def get_state(self, bot_id: str) -> dict | None:
        """bot_id의 현재 상태를 반환합니다. 없으면 None."""
        # TODO(Phase 2a): SELECT * FROM bot_states WHERE bot_id = ? 구현
        raise NotImplementedError("BotStateRepository.get_state — Phase 2a 구현 예정")

    async def update_state(self, bot_id: str, state: dict) -> None:
        """bot_id의 상태를 갱신합니다."""
        # TODO(Phase 2a): INSERT OR REPLACE INTO bot_states 구현
        raise NotImplementedError("BotStateRepository.update_state — Phase 2a 구현 예정")

    async def get_all_alive(self) -> list[dict]:
        """is_alive=True인 모든 봇 상태 목록을 반환합니다."""
        # TODO(Phase 2a): SELECT * FROM bot_states WHERE is_alive = 1 구현
        raise NotImplementedError("BotStateRepository.get_all_alive — Phase 2a 구현 예정")

    async def mark_dead(self, bot_id: str) -> None:
        """bot_id의 is_alive를 False로 설정합니다."""
        # TODO(Phase 2a): UPDATE bot_states SET is_alive = 0 WHERE bot_id = ? 구현
        raise NotImplementedError("BotStateRepository.mark_dead — Phase 2a 구현 예정")
