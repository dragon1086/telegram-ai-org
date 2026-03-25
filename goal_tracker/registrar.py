"""MeetingActionRegistrar — 회의 조치사항 GoalTracker 자동 등록 클래스.

역할:
    1. MeetingEvent에서 추출된 ActionItem을 GoalTracker 태스크 형식으로 변환
    2. GoalTracker.start_goal() 또는 기존 active goal에 서브태스크로 주입
    3. 상태머신의 IDLE 상태로 신규 태스크 주입 연동 인터페이스 제공
    4. 중복 등록 방지 (동일 회의에서 동일 태스크 재등록 방지)

등록 전략:
    - DAILY_RETRO   → 당일 회고 목표(goal)에 서브태스크로 등록
    - WEEKLY_MEETING → 주간 목표(goal)에 서브태스크로 등록
    - 기존 active goal 없으면 신규 goal 생성 후 서브태스크 등록
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import date, datetime, timezone
from typing import Awaitable, Callable, Optional


def _utcnow() -> datetime:
    """timezone-aware UTC datetime (Python 3.14+ 호환)."""
    return datetime.now(timezone.utc)

from loguru import logger

from goal_tracker.action_parser import ActionItem
from goal_tracker.meeting_handler import MeetingEvent, MeetingType
from goal_tracker.router import DeptRouter
from goal_tracker.state_machine import GoalTrackerStateMachine, GoalTrackerState


class MeetingActionRegistrar:
    """회의 조치사항을 GoalTracker에 자동 등록.

    GoalTracker 인스턴스와 연동하여 회의에서 추출된 액션아이템을
    GoalTracker 태스크 형식으로 변환·등록한다.

    사용 예::

        registrar = MeetingActionRegistrar(
            goal_tracker=tracker,
            router=DeptRouter(),
            org_id="aiorg_pm_bot",
        )
        await registrar.register_from_event(meeting_event)
    """

    def __init__(
        self,
        goal_tracker=None,           # core.goal_tracker.GoalTracker 인스턴스
        router: DeptRouter | None = None,
        org_id: str = "aiorg_pm_bot",
        send_func: Callable[[int, str], Awaitable[None]] | None = None,
        dedup_ttl_sec: float = 3600.0,   # 중복 방지 TTL (초), 기본 1시간
    ) -> None:
        self._tracker = goal_tracker
        self._router = router or DeptRouter()
        self._org_id = org_id
        self._send: Callable[[int, str], Awaitable[None]] = (
            send_func or _noop_send
        )
        self._dedup_ttl = dedup_ttl_sec
        # 중복 방지 캐시: hash(description) → registered_at timestamp
        self._registered: dict[str, datetime] = {}

    # ── 메인 등록 진입점 ───────────────────────────────────────────────────

    async def register_from_event(self, event: MeetingEvent) -> list[str]:
        """MeetingEvent의 ActionItem들을 GoalTracker에 일괄 등록.

        Args:
            event: MeetingEventHandler에서 감지된 회의 이벤트.

        Returns:
            등록된 goal_id 또는 task_id 리스트.
        """
        if not event.action_items:
            logger.debug(
                f"[Registrar] {event.display_name} — 등록할 액션아이템 없음"
            )
            return []

        # 중복 필터링
        new_items = self._filter_duplicates(event.action_items)
        if not new_items:
            logger.info(
                f"[Registrar] {event.display_name} — 모두 중복, 등록 생략"
            )
            return []

        logger.info(
            f"[Registrar] {event.display_name} — "
            f"{len(new_items)}개 액션아이템 GoalTracker 등록 시작"
        )

        registered_ids: list[str] = []
        chat_id = event.chat_id

        for item in new_items:
            try:
                goal_id = await self._register_single_item(item, event, chat_id)
                if goal_id:
                    registered_ids.append(goal_id)
                    self._mark_registered(item)
            except Exception as e:
                logger.error(
                    f"[Registrar] 액션아이템 등록 실패: {item.description[:50]} — {e}"
                )

        if registered_ids:
            await self._notify_registration(chat_id, event, registered_ids)

        return registered_ids

    async def register_single(
        self,
        description: str,
        assigned_dept: Optional[str] = None,
        chat_id: int = 0,
        meeting_type: MeetingType = MeetingType.UNKNOWN,
        due_date: Optional[str] = None,
        priority: str = "medium",
    ) -> Optional[str]:
        """단일 조치사항을 GoalTracker에 직접 등록.

        Args:
            description: 태스크 설명.
            assigned_dept: 담당 부서 org_id (None이면 자동 라우팅).
            chat_id: Telegram 채팅방 ID.
            meeting_type: 회의 유형.
            due_date: 마감일 ("YYYY-MM-DD").
            priority: 우선순위 ("high"|"medium"|"low").

        Returns:
            등록된 goal_id 또는 None.
        """
        item = ActionItem(
            description=description,
            assigned_dept=assigned_dept,
            due_date=due_date,
            priority=priority,
        )
        dummy_event = MeetingEvent(
            meeting_type=meeting_type,
            chat_id=chat_id,
            message_text=description,
            sender_org=self._org_id,
            action_items=[item],
        )
        ids = await self.register_from_event(dummy_event)
        return ids[0] if ids else None

    async def inject_to_state_machine(
        self,
        state_machine: GoalTrackerStateMachine,
        action_items: list[ActionItem],
    ) -> bool:
        """상태머신 IDLE 상태에 신규 태스크 주입.

        상태머신이 IDLE 상태일 때 새로운 액션아이템을 넣어 EVALUATE 사이클을 트리거.

        Args:
            state_machine: 대상 상태머신 (IDLE 상태여야 함).
            action_items: 주입할 액션아이템 목록.

        Returns:
            True if 주입 성공 (IDLE 상태였을 때), False otherwise.
        """
        if state_machine.state != GoalTrackerState.IDLE:
            logger.warning(
                f"[Registrar] inject_to_state_machine 실패: "
                f"IDLE 아님 (현재: {state_machine.state})"
            )
            return False

        if not action_items:
            return False

        # IDLE → EVALUATE 전이를 직접 트리거
        if not state_machine.start_evaluate():
            logger.warning(
                f"[Registrar] {state_machine.goal_id} EVALUATE 진입 불가 "
                f"(터미널 상태)"
            )
            return False

        logger.info(
            f"[Registrar] {state_machine.goal_id} 상태머신에 "
            f"{len(action_items)}개 태스크 주입 — EVALUATE 전이 완료"
        )
        return True

    # ── 내부 등록 로직 ────────────────────────────────────────────────────

    async def _register_single_item(
        self,
        item: ActionItem,
        event: MeetingEvent,
        chat_id: int,
    ) -> Optional[str]:
        """단일 ActionItem → GoalTracker 등록."""
        if self._tracker is None:
            logger.warning("[Registrar] GoalTracker 인스턴스 없음 — 등록 생략")
            return None

        # 담당 부서 결정 (없으면 자동 라우팅)
        assigned_dept = item.assigned_dept or self._router.route(item.description)

        # 목표 제목/설명 생성
        title = self._build_title(item, event)
        description = self._build_description(item, event, assigned_dept)

        # 메타데이터
        meta = {
            "meeting_type": event.meeting_type.value,
            "source_meeting": event.display_name,
            "assigned_dept": assigned_dept,
            "priority": item.priority,
            "registered_at": _utcnow().isoformat(),
        }
        if item.due_date:
            meta["due_date"] = item.due_date

        goal_id = await self._tracker.start_goal(
            title=title,
            description=description,
            meta=meta,
            chat_id=chat_id,
            org_id=self._org_id,
        )

        logger.info(
            f"[Registrar] 등록 완료: {goal_id} — {title[:60]} "
            f"(담당: {assigned_dept})"
        )
        return goal_id

    def _build_title(self, item: ActionItem, event: MeetingEvent) -> str:
        """Goal 제목 생성 (회의 유형 + 날짜 + 액션아이템 요약)."""
        today = date.today().isoformat()
        prefix = {
            MeetingType.DAILY_RETRO: f"[일일회고 {today}]",
            MeetingType.WEEKLY_MEETING: f"[주간회의 {today}]",
            MeetingType.UNKNOWN: f"[회의 {today}]",
        }.get(event.meeting_type, f"[회의 {today}]")

        # 설명 첫 30자를 제목으로
        short_desc = item.description[:40].rstrip()
        return f"{prefix} {short_desc}"

    def _build_description(
        self,
        item: ActionItem,
        event: MeetingEvent,
        assigned_dept: str,
    ) -> str:
        """Goal 상세 설명 생성."""
        lines = [
            f"## {item.description}",
            "",
            f"**출처**: {event.display_name}",
            f"**담당**: {assigned_dept}",
        ]
        if item.due_date:
            lines.append(f"**기한**: {item.due_date}")
        if item.priority != "medium":
            lines.append(f"**우선순위**: {item.priority}")
        if item.source_text and item.source_text != item.description:
            lines.extend(["", "**원문**:", f"> {item.source_text[:200]}"])
        return "\n".join(lines)

    # ── 중복 방지 ─────────────────────────────────────────────────────────

    def _filter_duplicates(self, items: list[ActionItem]) -> list[ActionItem]:
        """TTL 내 이미 등록된 항목 필터링."""
        now = _utcnow()
        result: list[ActionItem] = []
        for item in items:
            key = self._item_hash(item)
            last_reg = self._registered.get(key)
            if last_reg is None:
                result.append(item)
            else:
                elapsed = (now - last_reg).total_seconds()
                if elapsed > self._dedup_ttl:
                    result.append(item)
                else:
                    logger.debug(
                        f"[Registrar] 중복 스킵: {item.description[:40]} "
                        f"(last: {elapsed:.0f}s ago)"
                    )
        return result

    def _mark_registered(self, item: ActionItem) -> None:
        """등록 완료 표시."""
        key = self._item_hash(item)
        self._registered[key] = _utcnow()

    @staticmethod
    def _item_hash(item: ActionItem) -> str:
        """ActionItem 동일성 해시 (description 기반)."""
        return hashlib.sha256(item.description.strip().lower().encode()).hexdigest()[:16]

    # ── 알림 ──────────────────────────────────────────────────────────────

    async def _notify_registration(
        self,
        chat_id: int,
        event: MeetingEvent,
        registered_ids: list[str],
    ) -> None:
        """GoalTracker 등록 완료 알림."""
        if chat_id == 0:
            return
        msg = (
            f"✅ **{event.display_name}** 조치사항 GoalTracker 등록 완료\n"
            f"  등록된 목표: **{len(registered_ids)}개**\n"
            + "\n".join(f"  - {gid}" for gid in registered_ids[:5])
        )
        try:
            await self._send(chat_id, msg)
        except Exception as e:
            logger.warning(f"[Registrar] 알림 전송 실패: {e}")

    # ── 상태 조회 ─────────────────────────────────────────────────────────

    def clear_cache(self) -> None:
        """중복 방지 캐시 초기화 (테스트 또는 수동 초기화용)."""
        self._registered.clear()

    @property
    def registered_count(self) -> int:
        """누적 등록 항목 수 (캐시 기준)."""
        return len(self._registered)


async def _noop_send(chat_id: int, text: str) -> None:  # pragma: no cover
    pass
