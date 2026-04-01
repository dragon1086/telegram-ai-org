"""core.dashboard.models — 티켓 처리 현황 데이터 모델 (Phase 1).

TicketStatus 데이터클래스:
    - ticket_id   : 티켓 고유 식별자
    - state       : 상태 (pending / in_progress / done / blocked)
    - assignee    : 담당자 (조직 ID 또는 봇 이름)
    - created_at  : 생성 시각 (epoch float)
    - started_at  : 작업 시작 시각 (None = 미시작)
    - completed_at: 작업 완료 시각 (None = 미완료)
    - title       : 티켓 요약 제목 (선택)
    - org_id      : 담당 조직 ID (선택)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TicketState(str, Enum):
    """티켓 상태 열거형."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"

    # 색상 매핑 (만화 컨셉)
    @property
    def color(self) -> str:
        _map = {
            "pending": "#FFE000",      # 노랑
            "in_progress": "#0057FF",  # 파랑
            "done": "#00C851",         # 초록
            "blocked": "#FF3B3F",      # 빨강
        }
        return _map[self.value]

    # 캐릭터 이모지 매핑
    @property
    def emoji(self) -> str:
        _map = {
            "pending": "⏳",
            "in_progress": "⚡",
            "done": "✅",
            "blocked": "🚫",
        }
        return _map[self.value]


@dataclass
class TicketStatus:
    """티켓 처리 현황 데이터 모델.

    Attributes:
        ticket_id:    티켓 고유 ID (예: T-aiorg_pm_bot-1059)
        state:        현재 상태 (TicketState)
        assignee:     담당자 ID (예: aiorg_engineering_bot)
        created_at:   생성 시각 (epoch float, 기본=현재)
        started_at:   작업 시작 시각 (None = 미시작)
        completed_at: 작업 완료 시각 (None = 미완료)
        title:        요약 제목
        org_id:       담당 조직 ID

    Example::

        ticket = TicketStatus(
            ticket_id="T-001",
            state=TicketState.IN_PROGRESS,
            assignee="aiorg_engineering_bot",
            title="대시보드 구현",
        )
    """

    ticket_id: str
    state: TicketState = TicketState.PENDING
    assignee: str = "unassigned"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    title: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        # 문자열로 받아도 TicketState로 변환
        if isinstance(self.state, str):
            self.state = TicketState(self.state)

    # ------------------------------------------------------------------
    # 상태 전환 헬퍼
    # ------------------------------------------------------------------

    def start(self) -> "TicketStatus":
        """pending → in_progress 전환."""
        self.state = TicketState.IN_PROGRESS
        self.started_at = time.time()
        return self

    def complete(self) -> "TicketStatus":
        """in_progress → done 전환."""
        self.state = TicketState.DONE
        self.completed_at = time.time()
        if self.started_at is None:
            self.started_at = self.created_at
        return self

    def block(self) -> "TicketStatus":
        """→ blocked 전환."""
        self.state = TicketState.BLOCKED
        return self

    # ------------------------------------------------------------------
    # 직렬화
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """JSON 직렬화용 딕셔너리 변환."""
        return {
            "ticket_id": self.ticket_id,
            "state": self.state.value,
            "assignee": self.assignee,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "title": self.title,
            "org_id": self.org_id,
            "color": self.state.color,
            "emoji": self.state.emoji,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TicketStatus":
        """딕셔너리에서 TicketStatus 생성."""
        return cls(
            ticket_id=data["ticket_id"],
            state=TicketState(data.get("state", "pending")),
            assignee=data.get("assignee", "unassigned"),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            title=data.get("title", ""),
            org_id=data.get("org_id", ""),
        )

    # ------------------------------------------------------------------
    # 집계용 속성
    # ------------------------------------------------------------------

    @property
    def duration_seconds(self) -> Optional[float]:
        """작업 소요 시간 (초). 완료된 티켓만 유효."""
        if self.started_at is not None and self.completed_at is not None:
            return self.completed_at - self.started_at
        return None

    @property
    def is_done(self) -> bool:
        return self.state == TicketState.DONE

    @property
    def is_active(self) -> bool:
        return self.state == TicketState.IN_PROGRESS


# ---------------------------------------------------------------------------
# 부서별 캐릭터 매핑 (만화 컨셉)
# ---------------------------------------------------------------------------

ORG_CHARACTERS: dict[str, dict] = {
    "aiorg_engineering_bot": {"emoji": "🦾", "name": "개발실", "color": "#0057FF"},
    "aiorg_design_bot":      {"emoji": "🎨", "name": "디자인실", "color": "#9B00FF"},
    "aiorg_product_bot":     {"emoji": "📋", "name": "기획실", "color": "#FF6B00"},
    "aiorg_ops_bot":         {"emoji": "⚙️", "name": "운영실", "color": "#00C851"},
    "aiorg_growth_bot":      {"emoji": "📈", "name": "성장실", "color": "#FFE000"},
    "aiorg_research_bot":    {"emoji": "🔬", "name": "리서치실", "color": "#FF3B3F"},
    "aiorg_pm_bot":          {"emoji": "🎯", "name": "PM실", "color": "#FFFFFF"},
}


def get_character(org_id: str) -> dict:
    """org_id에 해당하는 캐릭터 정보를 반환. 미등록 시 기본값."""
    return ORG_CHARACTERS.get(
        org_id,
        {"emoji": "🤖", "name": org_id or "Unknown", "color": "#888888"},
    )
