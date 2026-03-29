"""core.types — 공유 타입 별칭, TypedDict, 상수 (Phase 1-B 스캐폴딩).

이 모듈은 순수 타입 정의만 포함합니다.
비즈니스 로직이나 core 내부 모듈 임포트는 금지합니다.
"""
from __future__ import annotations

from typing import Literal, TypedDict

# ---------------------------------------------------------------------------
# 기본 타입 별칭
# ---------------------------------------------------------------------------

TaskID = str
"""태스크 고유 식별자 (UUID 또는 slug 문자열)."""

OrgID = str
"""조직(팀) 고유 식별자 (예: 'dev', 'ops', 'design')."""

BotHandle = str
"""Telegram 봇 핸들 (예: '@dev_bot')."""

# ---------------------------------------------------------------------------
# Literal 타입
# ---------------------------------------------------------------------------

TaskStatusLiteral = Literal[
    "pending",
    "in_progress",
    "done",
    "failed",
    "cancelled",
]
"""태스크 상태값 Literal 타입."""

EngineType = Literal["claude-code", "codex", "gemini-cli"]
"""지원하는 LLM 엔진 종류."""

# ---------------------------------------------------------------------------
# TypedDict 정의
# ---------------------------------------------------------------------------


class MessageEnvelope(TypedDict):
    """봇 간 또는 서비스 간 메시지 전달 봉투."""

    to: OrgID
    from_: OrgID
    task_id: TaskID
    content: str
    msg_type: str
    timestamp: str  # ISO 8601 형식


class BotState(TypedDict):
    """봇 런타임 상태 스냅샷."""

    bot_id: str
    org_id: OrgID
    is_alive: bool
    last_seen: str  # ISO 8601 형식
    engine: EngineType


# ---------------------------------------------------------------------------
# 재-내보내기 노트
# ---------------------------------------------------------------------------

# ExecutionMode 실제 구현체는 core.dynamic_team_builder 에 있습니다.
# 여기서 임포트하면 순환 참조가 발생하므로 직접 참조 시
#   from core.dynamic_team_builder import ExecutionMode
# 를 사용하십시오.
