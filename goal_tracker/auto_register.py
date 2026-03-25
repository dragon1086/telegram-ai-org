"""GoalTracker 자동 등록 모듈 — 보고 텍스트에서 조치사항을 GoalTracker에 자동 주입.

`auto_register_from_report(report_text, report_type)` 함수가 메인 진입점이다.

동작 흐름:
    1. report_parser.parse_action_items() 로 조치사항 추출
    2. MeetingEvent 생성
    3. MeetingActionRegistrar 또는 GoalTracker.start_goal()로 등록
    4. 상태머신이 제공되면 IDLE 상태에서 EVALUATE 사이클 트리거

경량 사용 (GoalTracker 없이 파싱만):
    items = parse_action_items(text, "daily_retro")
    # ActionItem 리스트 반환 — 등록 없이 파싱 결과만 확인 가능

완전 등록 사용:
    result = await auto_register_from_report(
        report_text=text,
        report_type="weekly_meeting",
        goal_tracker=tracker,
        state_machine=sm,
        chat_id=CHAT_ID,
        org_id="aiorg_pm_bot",
    )
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from loguru import logger

from goal_tracker.action_parser import ActionItem
from goal_tracker.meeting_handler import MeetingEvent
from goal_tracker.report_parser import (
    _normalize_report_type,
    parse_action_items,
    parse_report_metadata,
)
from goal_tracker.state_machine import GoalTrackerState, GoalTrackerStateMachine


def _utcnow() -> datetime:
    """timezone-aware UTC datetime (Python 3.14+ 호환)."""
    return datetime.now(timezone.utc)

# ── 결과 데이터클래스 ─────────────────────────────────────────────────────────

@dataclass
class AutoRegisterResult:
    """auto_register_from_report 실행 결과."""

    report_type: str
    meeting_type: str
    action_items_found: int
    registered_ids: list[str] = field(default_factory=list)
    state_machine_triggered: bool = False
    errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    registered_at: datetime = field(default_factory=_utcnow)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def registered_count(self) -> int:
        return len(self.registered_ids)

    def __str__(self) -> str:
        return (
            f"AutoRegisterResult("
            f"type={self.report_type}, "
            f"found={self.action_items_found}, "
            f"registered={self.registered_count}, "
            f"sm_triggered={self.state_machine_triggered})"
        )


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

async def auto_register_from_report(
    report_text: str,
    report_type: str,
    *,
    goal_tracker=None,          # core.goal_tracker.GoalTracker 인스턴스 (선택)
    registrar=None,             # goal_tracker.registrar.MeetingActionRegistrar (선택)
    state_machine: Optional[GoalTrackerStateMachine] = None,
    chat_id: int = 0,
    org_id: str = "aiorg_pm_bot",
    send_func: Optional[Callable[[int, str], Awaitable[None]]] = None,
    min_confidence: float = 0.0,
) -> AutoRegisterResult:
    """보고 텍스트를 파싱하여 GoalTracker에 조치사항을 자동 등록.

    Args:
        report_text:   일일회고/주간회의 전체 텍스트.
        report_type:   "daily_retro" | "weekly_meeting" | 기타.
        goal_tracker:  GoalTracker 인스턴스 (없으면 파싱만 수행).
        registrar:     MeetingActionRegistrar 인스턴스 (goal_tracker보다 우선).
        state_machine: 주입 후 EVALUATE 사이클을 트리거할 상태머신.
        chat_id:       Telegram 채팅방 ID.
        org_id:        요청 조직 ID.
        send_func:     Telegram 메시지 전송 함수.
        min_confidence: 이 값 미만 confidence 아이템 제외.

    Returns:
        AutoRegisterResult 인스턴스.
    """
    meeting_type_enum = _normalize_report_type(report_type)
    result = AutoRegisterResult(
        report_type=report_type,
        meeting_type=meeting_type_enum.value,
        action_items_found=0,
    )

    if not report_text or not report_text.strip():
        logger.warning(f"[AutoRegister] 빈 보고 텍스트 — 처리 생략 (type={report_type})")
        return result

    # ── Step 1: 파싱 ───────────────────────────────────────────────────────
    action_items = parse_action_items(
        report_text, report_type, min_confidence=min_confidence
    )
    result.action_items_found = len(action_items)
    result.metadata = parse_report_metadata(report_text, report_type)

    logger.info(
        f"[AutoRegister] {report_type} 파싱 완료 — "
        f"{len(action_items)}개 조치사항 추출"
    )

    if not action_items:
        logger.info(f"[AutoRegister] 등록할 조치사항 없음 (type={report_type})")
        return result

    # ── Step 2: 등록 ───────────────────────────────────────────────────────
    meeting_event = MeetingEvent(
        meeting_type=meeting_type_enum,
        chat_id=chat_id,
        message_text=report_text,
        sender_org=org_id,
        action_items=action_items,
        metadata=result.metadata,
    )

    if registrar is not None:
        # MeetingActionRegistrar 경로 (권장)
        try:
            registered_ids = await registrar.register_from_event(meeting_event)
            result.registered_ids = registered_ids
        except Exception as e:
            err = f"registrar.register_from_event 실패: {e}"
            logger.error(f"[AutoRegister] {err}")
            result.errors.append(err)

    elif goal_tracker is not None:
        # GoalTracker 직접 등록 경로 (fallback)
        for item in action_items:
            try:
                goal_id = await _register_item_direct(
                    item=item,
                    meeting_event=meeting_event,
                    goal_tracker=goal_tracker,
                    org_id=org_id,
                )
                if goal_id:
                    result.registered_ids.append(goal_id)
            except Exception as e:
                err = f"직접 등록 실패 ({item.description[:40]}): {e}"
                logger.error(f"[AutoRegister] {err}")
                result.errors.append(err)

    else:
        logger.info("[AutoRegister] goal_tracker/registrar 없음 — 파싱 결과만 반환")

    # ── Step 3: 상태머신 DISPATCH 주입 ─────────────────────────────────────
    if state_machine is not None and result.registered_ids:
        triggered = _inject_to_state_machine(state_machine, result.registered_ids)
        result.state_machine_triggered = triggered

    # ── Step 4: 완료 알림 ──────────────────────────────────────────────────
    if send_func and result.registered_ids and chat_id:
        try:
            type_label = {
                "daily_retro": "일일회고",
                "weekly_meeting": "주간회의",
            }.get(meeting_type_enum.value, "회의")
            msg = (
                f"✅ **{type_label}** 조치사항 자동 등록 완료\n"
                f"  파싱: {result.action_items_found}개 → "
                f"등록: {result.registered_count}개\n"
                + "".join(f"  - {gid}\n" for gid in result.registered_ids[:5])
            )
            await send_func(chat_id, msg)
        except Exception as e:
            logger.warning(f"[AutoRegister] 알림 전송 실패: {e}")

    logger.info(f"[AutoRegister] 완료: {result}")
    return result


# ── 동기 편의 래퍼 ────────────────────────────────────────────────────────────

def auto_register_from_report_sync(
    report_text: str,
    report_type: str,
    **kwargs,
) -> AutoRegisterResult:
    """동기 환경에서 `auto_register_from_report` 호출 편의 래퍼.

    이미 실행 중인 이벤트 루프가 있으면 그 루프에서, 없으면 새 루프를 생성.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 실행 중인 루프 — asyncio.ensure_future 권장이지만
            # 동기 호출이 필요한 경우 concurrent.futures로 처리
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    auto_register_from_report(report_text, report_type, **kwargs),
                )
                return future.result()
        else:
            return loop.run_until_complete(
                auto_register_from_report(report_text, report_type, **kwargs)
            )
    except RuntimeError:
        return asyncio.run(
            auto_register_from_report(report_text, report_type, **kwargs)
        )


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

async def _register_item_direct(
    item: ActionItem,
    meeting_event: MeetingEvent,
    goal_tracker,
    org_id: str,
) -> Optional[str]:
    """GoalTracker.start_goal()로 단일 ActionItem 직접 등록."""
    from datetime import date as _date

    today = _date.today().isoformat()
    type_label = meeting_event.display_name
    title = f"[{type_label} {today}] {item.description[:40]}"
    description_lines = [
        f"## {item.description}",
        "",
        f"**출처**: {type_label}",
    ]
    if item.assigned_dept:
        description_lines.append(f"**담당**: {item.assigned_dept}")
    if item.due_date:
        description_lines.append(f"**기한**: {item.due_date}")
    if item.priority != "medium":
        description_lines.append(f"**우선순위**: {item.priority}")

    description = "\n".join(description_lines)
    meta = {
        "meeting_type": meeting_event.meeting_type.value,
        "source": type_label,
        "priority": item.priority,
        "registered_at": _utcnow().isoformat(),
    }
    if item.assigned_dept:
        meta["assigned_dept"] = item.assigned_dept
    if item.due_date:
        meta["due_date"] = item.due_date

    goal_id = await goal_tracker.start_goal(
        title=title,
        description=description,
        meta=meta,
        chat_id=meeting_event.chat_id,
        org_id=org_id,
    )
    return goal_id


def _inject_to_state_machine(
    sm: GoalTrackerStateMachine,
    task_ids: list[str],
) -> bool:
    """상태머신이 IDLE이면 EVALUATE 사이클 트리거 (dispatch 준비 주입).

    등록된 goal_id 목록을 dispatch 이벤트로 넘기거나,
    IDLE 상태에서 start_evaluate()를 호출한다.
    """
    if sm.state != GoalTrackerState.IDLE:
        logger.debug(
            f"[AutoRegister] 상태머신 주입 스킵 — IDLE 아님 (state={sm.state})"
        )
        return False

    triggered = sm.start_evaluate()
    if triggered:
        logger.info(
            f"[AutoRegister] {sm.goal_id} 상태머신 EVALUATE 트리거 "
            f"— {len(task_ids)}개 태스크 등록 후"
        )
    return triggered
