"""회의 이벤트 핸들러 — 일일회고/주간회의 트리거 감지 및 멀티봇 참여.

역할:
    1. 회의 이벤트 감지: 텔레그램 메시지에서 일일회고/주간회의 트리거 인식
    2. 회의 채널 메시지 수신: 각 봇이 회의 채널 메시지를 수신하는 인터페이스
    3. 액션아이템 추출: ActionParser로 조치사항 파싱
    4. GoalTracker 주입: MeetingActionRegistrar를 통해 idle 상태로 신규 태스크 주입

회의 트리거 패턴:
    일일회고: "일일회고", "daily retro", "데일리", "#daily", "오늘의 회고"
    주간회의: "주간회의", "weekly meeting", "주간 미팅", "스탠드업", "#weekly"

멀티봇 참여 인터페이스:
    각 조직 봇은 MeetingEventHandler.on_message()를 통해
    회의 채널 메시지를 수신하고 GoalTracker에 태스크를 주입한다.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Awaitable, Callable, Optional

from loguru import logger

from goal_tracker.action_parser import ActionItem, ActionParser


class MeetingType(str, Enum):
    """회의 유형."""

    DAILY_RETRO = "daily_retro"    # 일일회고
    WEEKLY_MEETING = "weekly_meeting"  # 주간회의
    UNKNOWN = "unknown"


@dataclass
class MeetingEvent:
    """감지된 회의 이벤트."""

    meeting_type: MeetingType
    chat_id: int
    message_text: str
    sender_org: str                        # 메시지 발신 봇 org_id
    triggered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    action_items: list[ActionItem] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def has_action_items(self) -> bool:
        return len(self.action_items) > 0

    @property
    def display_name(self) -> str:
        mapping = {
            MeetingType.DAILY_RETRO: "일일회고",
            MeetingType.WEEKLY_MEETING: "주간회의",
            MeetingType.UNKNOWN: "회의",
        }
        return mapping.get(self.meeting_type, "회의")


# ── 회의 트리거 패턴 ──────────────────────────────────────────────────────────

_DAILY_RETRO_PATTERNS = [
    r"일일\s*회고",
    r"daily\s+retro",
    r"데일리\s*리뷰?",
    r"오늘의\s*회고",
    r"#daily",
    r"daily\s+review",
    r"오늘\s*회고",
]

_WEEKLY_MEETING_PATTERNS = [
    r"주간\s*회의",
    r"weekly\s+meeting",
    r"주간\s*미팅",
    r"스탠드\s*업",
    r"standup",
    r"#weekly",
    r"주간\s*보고",
    r"weekly\s+standup",
    r"주간회의\s*시작",
]

_COMPILED_DAILY = re.compile(
    "|".join(_DAILY_RETRO_PATTERNS), re.IGNORECASE
)
_COMPILED_WEEKLY = re.compile(
    "|".join(_WEEKLY_MEETING_PATTERNS), re.IGNORECASE
)


def detect_meeting_type(text: str) -> MeetingType:
    """메시지에서 회의 유형 감지.

    Args:
        text: 텔레그램 메시지 원문.

    Returns:
        MeetingType enum 값.
    """
    if _COMPILED_DAILY.search(text):
        return MeetingType.DAILY_RETRO
    if _COMPILED_WEEKLY.search(text):
        return MeetingType.WEEKLY_MEETING
    return MeetingType.UNKNOWN


class MeetingEventHandler:
    """회의 이벤트 핸들러 — 멀티봇 채팅 참여 인터페이스.

    각 조직 봇은 이 핸들러를 통해 회의 채널 메시지를 수신하고
    GoalTracker에 조치사항 태스크를 주입한다.

    사용 예::

        handler = MeetingEventHandler(
            org_id="aiorg_engineering_bot",
            registrar=my_registrar,
        )
        # 텔레그램 메시지 수신 시 호출
        await handler.on_message(chat_id=GROUP_CHAT_ID, text=message_text)
    """

    def __init__(
        self,
        org_id: str,
        registrar=None,  # MeetingActionRegistrar (lazy to avoid circular)
        parser: ActionParser | None = None,
        send_func: Callable[[int, str], Awaitable[None]] | None = None,
        enabled: bool = True,
    ) -> None:
        self._org_id = org_id
        self._registrar = registrar
        self._parser = parser or ActionParser()
        self._send: Callable[[int, str], Awaitable[None]] = (
            send_func or _noop_send
        )
        self._enabled = enabled
        self._last_event: Optional[MeetingEvent] = None
        self._processed_count = 0

    # ── 메인 진입점 ───────────────────────────────────────────────────────

    async def on_message(
        self,
        chat_id: int,
        text: str,
        sender_org: str = "",
        metadata: dict | None = None,
    ) -> Optional[MeetingEvent]:
        """텔레그램 메시지 수신 핸들러.

        회의 트리거 감지 시 ActionParser로 파싱 후 MeetingActionRegistrar에 전달.

        Args:
            chat_id: Telegram 채팅방 ID.
            text: 메시지 원문.
            sender_org: 발신 봇 org_id (없으면 self._org_id 사용).
            metadata: 추가 메타데이터.

        Returns:
            MeetingEvent (회의 트리거 감지 시) 또는 None.
        """
        if not self._enabled:
            return None

        meeting_type = detect_meeting_type(text)
        if meeting_type == MeetingType.UNKNOWN:
            # 회의 트리거 없음 → 현재 진행 중인 회의에 액션아이템 포함 여부 확인
            if self._last_event and self._parser.has_action_items(text):
                meeting_type = self._last_event.meeting_type
            else:
                return None

        # 액션아이템 파싱
        action_items = self._parser.parse(text)

        event = MeetingEvent(
            meeting_type=meeting_type,
            chat_id=chat_id,
            message_text=text,
            sender_org=sender_org or self._org_id,
            action_items=action_items,
            metadata=metadata or {},
        )

        self._last_event = event
        self._processed_count += 1

        logger.info(
            f"[MeetingHandler:{self._org_id}] {event.display_name} 감지 — "
            f"액션아이템 {len(action_items)}개"
        )

        # GoalTracker에 자동 등록
        if action_items and self._registrar is not None:
            await self._registrar.register_from_event(event)

        return event

    async def on_daily_retro_start(
        self,
        chat_id: int,
        summary_text: str = "",
    ) -> MeetingEvent:
        """일일회고 시작 이벤트 직접 발생 (cron 스케줄러 호출용).

        scripts/daily_retro.py 에서 직접 호출하여 GoalTracker 주입 트리거.
        """
        event = MeetingEvent(
            meeting_type=MeetingType.DAILY_RETRO,
            chat_id=chat_id,
            message_text=summary_text,
            sender_org=self._org_id,
            action_items=self._parser.parse(summary_text) if summary_text else [],
        )
        self._last_event = event
        logger.info(
            f"[MeetingHandler:{self._org_id}] 일일회고 이벤트 발생 "
            f"— 액션아이템 {len(event.action_items)}개"
        )
        if event.action_items and self._registrar is not None:
            await self._registrar.register_from_event(event)
        return event

    async def on_weekly_meeting_start(
        self,
        chat_id: int,
        summary_text: str = "",
    ) -> MeetingEvent:
        """주간회의 시작 이벤트 직접 발생 (cron 스케줄러 호출용).

        scripts/weekly_meeting_multibot.py 에서 직접 호출.
        """
        event = MeetingEvent(
            meeting_type=MeetingType.WEEKLY_MEETING,
            chat_id=chat_id,
            message_text=summary_text,
            sender_org=self._org_id,
            action_items=self._parser.parse(summary_text) if summary_text else [],
        )
        self._last_event = event
        logger.info(
            f"[MeetingHandler:{self._org_id}] 주간회의 이벤트 발생 "
            f"— 액션아이템 {len(event.action_items)}개"
        )
        if event.action_items and self._registrar is not None:
            await self._registrar.register_from_event(event)
        return event

    # ── 상태 조회 ─────────────────────────────────────────────────────────

    @property
    def last_event(self) -> Optional[MeetingEvent]:
        return self._last_event

    @property
    def processed_count(self) -> int:
        return self._processed_count

    def reset(self) -> None:
        """상태 초기화 (테스트용)."""
        self._last_event = None
        self._processed_count = 0


async def _noop_send(chat_id: int, text: str) -> None:  # pragma: no cover
    pass
