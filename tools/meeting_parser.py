"""meeting_parser.py — 일일회고/주간회의 채팅 로그 파싱 도구 (tools 레이어).

`MeetingParser` 클래스가 메인 진입점이다.
내부적으로 `goal_tracker.action_parser.ActionParser` 와
`goal_tracker.meeting_handler` 를 사용한다.

사용 예::

    parser = MeetingParser()
    items = parser.parse(chat_log, meeting_type="daily_retro")
    for item in items:
        print(item.assignee, item.content, item.due_date)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from goal_tracker.action_parser import ActionItem, ActionParser
from goal_tracker.meeting_handler import detect_meeting_type

# ── 결과 데이터클래스 ─────────────────────────────────────────────────────────


@dataclass
class ParsedActionItem:
    """파싱된 조치사항 — MeetingParser 외부 인터페이스용.

    goal_tracker.action_parser.ActionItem 의 tools 레이어 래퍼.
    """

    content: str                         # 조치사항 내용
    assignee: Optional[str] = None       # 담당자 org_id (없으면 None)
    due_date: Optional[str] = None       # 마감일 "YYYY-MM-DD" (없으면 None)
    priority: str = "medium"             # "high" | "medium" | "low"
    source_text: str = ""                # 원문
    confidence: float = 1.0             # 파싱 신뢰도
    meeting_type: str = "unknown"        # "daily_retro" | "weekly_meeting" | "unknown"

    @classmethod
    def from_action_item(
        cls,
        item: ActionItem,
        meeting_type: str = "unknown",
    ) -> "ParsedActionItem":
        """ActionItem → ParsedActionItem 변환."""
        return cls(
            content=item.description,
            assignee=item.assigned_dept,
            due_date=item.due_date,
            priority=item.priority,
            source_text=item.source_text,
            confidence=item.confidence,
            meeting_type=meeting_type,
        )

    def to_action_item(self) -> ActionItem:
        """ParsedActionItem → ActionItem 역변환 (registrar 전달용)."""
        return ActionItem(
            description=self.content,
            assigned_dept=self.assignee,
            due_date=self.due_date,
            priority=self.priority,
            source_text=self.source_text,
            confidence=self.confidence,
        )

    def __str__(self) -> str:
        parts = [self.content[:60]]
        if self.assignee:
            parts.append(f"담당:{self.assignee}")
        if self.due_date:
            parts.append(f"기한:{self.due_date}")
        return " | ".join(parts)


# ── MeetingParser ──────────────────────────────────────────────────────────────


class MeetingParser:
    """일일회고/주간회의 채팅 로그 파싱 — 액션아이템(담당자, 내용, 기한) 추출.

    정규식 + 키워드 기반 파싱 ("→", "담당:", "조치:", "조치사항:" 패턴 지원).
    내부적으로 goal_tracker.action_parser.ActionParser 를 활용한다.

    Args:
        min_confidence: 이 값 미만 confidence 아이템 제외. 기본 0.0 (전체 포함).
        auto_detect_type: True 이면 chat_log 내용에서 회의 유형 자동 감지.

    사용 예::

        parser = MeetingParser()

        # 1. 회의 유형 명시
        items = parser.parse(chat_log, meeting_type="daily_retro")

        # 2. 자동 감지
        detected = parser.detect_type(chat_log)
        items = parser.parse(chat_log)  # auto_detect_type=True 기본값
    """

    def __init__(
        self,
        min_confidence: float = 0.0,
        auto_detect_type: bool = True,
    ) -> None:
        self._inner = ActionParser()
        self._min_confidence = min_confidence
        self._auto_detect = auto_detect_type

    # ── 메인 파싱 ─────────────────────────────────────────────────────────

    def parse(
        self,
        chat_log: str,
        meeting_type: str = "auto",
    ) -> list[ParsedActionItem]:
        """채팅 로그에서 조치사항 추출.

        Args:
            chat_log:     회의 채팅 로그 전문.
            meeting_type: "daily_retro" | "weekly_meeting" | "auto" (자동 감지).

        Returns:
            ParsedActionItem 리스트. 추출 실패 시 빈 리스트.
        """
        if not chat_log or not chat_log.strip():
            logger.debug("[MeetingParser] 빈 채팅 로그 — 빈 리스트 반환")
            return []

        # 회의 유형 결정
        resolved_type = self._resolve_type(chat_log, meeting_type)
        logger.info(
            f"[MeetingParser] 파싱 시작 — type={resolved_type}, "
            f"log_len={len(chat_log)}"
        )

        # ActionParser로 파싱
        raw_items: list[ActionItem] = self._inner.parse(chat_log)

        # ParsedActionItem 변환 + confidence 필터링
        result: list[ParsedActionItem] = []
        for item in raw_items:
            if item.confidence < self._min_confidence:
                logger.debug(
                    f"[MeetingParser] confidence 미달 스킵: "
                    f"{item.description[:40]} ({item.confidence:.2f})"
                )
                continue
            result.append(ParsedActionItem.from_action_item(item, meeting_type=resolved_type))

        logger.info(
            f"[MeetingParser] 파싱 완료 — "
            f"{len(raw_items)}개 후보 → {len(result)}개 추출 (type={resolved_type})"
        )
        return result

    def parse_line(self, line: str, meeting_type: str = "unknown") -> Optional[ParsedActionItem]:
        """단일 라인 파싱 (빠른 처리용).

        Args:
            line:         단일 채팅 메시지 라인.
            meeting_type: 회의 유형 레이블.

        Returns:
            ParsedActionItem 또는 None.
        """
        raw = self._inner.parse_line(line)
        if raw is None:
            return None
        return ParsedActionItem.from_action_item(raw, meeting_type=meeting_type)

    # ── 회의 유형 감지 ────────────────────────────────────────────────────

    def detect_type(self, chat_log: str) -> str:
        """채팅 로그에서 회의 유형 자동 감지.

        Returns:
            "daily_retro" | "weekly_meeting" | "unknown"
        """
        mt = detect_meeting_type(chat_log)
        return mt.value

    def _resolve_type(self, chat_log: str, meeting_type: str) -> str:
        """meeting_type 결정: 'auto' 이거나 self._auto_detect=True 이면 자동 감지."""
        if meeting_type == "auto" or (self._auto_detect and meeting_type == "unknown"):
            return self.detect_type(chat_log)
        return meeting_type

    # ── 유틸리티 ──────────────────────────────────────────────────────────

    def has_action_items(self, text: str) -> bool:
        """텍스트에 조치사항 키워드가 포함되어 있는지 빠른 검사."""
        return self._inner.has_action_items(text)

    def extract_meeting_summary(self, chat_log: str) -> dict:
        """채팅 로그에서 회의 요약 정보 추출.

        Returns:
            {
                "meeting_type": str,
                "action_item_count": int,
                "has_action_items": bool,
            }
        """
        items = self.parse(chat_log)
        return {
            "meeting_type": self.detect_type(chat_log),
            "action_item_count": len(items),
            "has_action_items": len(items) > 0,
        }
