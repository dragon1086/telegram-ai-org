"""goaltracker_client.py — GoalTracker API 연동 클라이언트 (tools 레이어).

`GoalTrackerClient.register_action_item(title, assignee, due_date, source)` 가
메인 진입점이다.

내부적으로 `goal_tracker.auto_register.auto_register_from_report` 와
`goal_tracker.registrar.MeetingActionRegistrar` 를 사용한다.

사용 예::

    client = GoalTrackerClient(org_id="aiorg_pm_bot")

    # 단일 등록
    goal_id = await client.register_action_item(
        title="API 인증 버그 수정",
        assignee="aiorg_engineering_bot",
        due_date="2026-03-31",
        source="daily_retro",
    )

    # 전체 보고 텍스트 일괄 등록
    result = await client.register_from_report(
        report_text=chat_log,
        report_type="weekly_meeting",
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from loguru import logger

from goal_tracker.auto_register import AutoRegisterResult, auto_register_from_report
from goal_tracker.meeting_handler import MeetingType
from goal_tracker.registrar import MeetingActionRegistrar
from goal_tracker.router import DeptRouter
from goal_tracker.state_machine import GoalTrackerStateMachine


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 등록 결과 ─────────────────────────────────────────────────────────────────


@dataclass
class RegisterResult:
    """GoalTrackerClient 단건 등록 결과."""

    goal_id: Optional[str]
    title: str
    assignee: Optional[str]
    due_date: Optional[str]
    source: str
    success: bool
    error: Optional[str] = None
    registered_at: datetime = field(default_factory=_utcnow)

    def __str__(self) -> str:
        status = f"OK({self.goal_id})" if self.success else f"FAIL({self.error})"
        return f"RegisterResult({self.title[:40]} | {status})"


# ── GoalTrackerClient ─────────────────────────────────────────────────────────


class GoalTrackerClient:
    """GoalTracker API 연동 클라이언트.

    회의 조치사항을 GoalTracker에 등록하는 tools 레이어 인터페이스.
    내부적으로 MeetingActionRegistrar + auto_register_from_report 를 사용한다.

    Args:
        org_id:       요청 조직 ID (기본: "aiorg_pm_bot").
        goal_tracker: core.goal_tracker.GoalTracker 인스턴스 (없으면 dry-run).
        state_machine: 등록 후 EVALUATE 사이클을 트리거할 상태머신.
        send_func:    Telegram 알림 전송 함수.
        chat_id:      기본 Telegram 채팅방 ID.
    """

    def __init__(
        self,
        org_id: str = "aiorg_pm_bot",
        goal_tracker=None,
        state_machine: Optional[GoalTrackerStateMachine] = None,
        send_func: Optional[Callable[[int, str], Awaitable[None]]] = None,
        chat_id: int = 0,
    ) -> None:
        self._org_id = org_id
        self._tracker = goal_tracker
        self._sm = state_machine
        self._send = send_func or _noop_send
        self._chat_id = chat_id
        self._router = DeptRouter()
        self._registrar = MeetingActionRegistrar(
            goal_tracker=goal_tracker,
            router=self._router,
            org_id=org_id,
            send_func=send_func,
        )
        # 등록 이력 (메모리 내 캐시)
        self._history: list[RegisterResult] = []

    # ── 단건 등록 ─────────────────────────────────────────────────────────

    async def register_action_item(
        self,
        title: str,
        assignee: Optional[str] = None,
        due_date: Optional[str] = None,
        source: str = "unknown",
        priority: str = "medium",
        chat_id: Optional[int] = None,
    ) -> RegisterResult:
        """단일 조치사항을 GoalTracker에 등록.

        Args:
            title:    조치사항 제목/내용.
            assignee: 담당자 org_id (예: "aiorg_engineering_bot").
                      None 이면 DeptRouter가 자동 라우팅.
            due_date: 마감일 "YYYY-MM-DD" 형식. None 허용.
            source:   출처 ("daily_retro" | "weekly_meeting" | 기타).
            priority: "high" | "medium" | "low".
            chat_id:  Telegram 채팅방 ID (None 이면 인스턴스 기본값 사용).

        Returns:
            RegisterResult 인스턴스.
        """
        effective_chat_id = chat_id if chat_id is not None else self._chat_id
        meeting_type = self._source_to_meeting_type(source)

        logger.info(
            f"[GoalTrackerClient] 단건 등록: title={title[:50]}, "
            f"assignee={assignee}, due_date={due_date}, source={source}"
        )

        try:
            goal_id = await self._registrar.register_single(
                description=title,
                assigned_dept=assignee,
                chat_id=effective_chat_id,
                meeting_type=meeting_type,
                due_date=due_date,
                priority=priority,
            )
            result = RegisterResult(
                goal_id=goal_id,
                title=title,
                assignee=assignee,
                due_date=due_date,
                source=source,
                success=goal_id is not None,
            )
            if goal_id:
                logger.info(
                    f"[GoalTrackerClient] 등록 완료: {goal_id} — {title[:50]}"
                )
            else:
                logger.warning(
                    f"[GoalTrackerClient] 등록 실패 (goal_id=None): {title[:50]}"
                )
        except Exception as e:
            logger.error(f"[GoalTrackerClient] 등록 예외: {e} — {title[:50]}")
            result = RegisterResult(
                goal_id=None,
                title=title,
                assignee=assignee,
                due_date=due_date,
                source=source,
                success=False,
                error=str(e),
            )

        self._history.append(result)
        return result

    # ── 보고 텍스트 일괄 등록 ─────────────────────────────────────────────

    async def register_from_report(
        self,
        report_text: str,
        report_type: str,
        chat_id: Optional[int] = None,
        min_confidence: float = 0.0,
    ) -> AutoRegisterResult:
        """보고 텍스트 전체를 파싱하여 조치사항을 일괄 GoalTracker 등록.

        Args:
            report_text:    일일회고/주간회의 전체 텍스트.
            report_type:    "daily_retro" | "weekly_meeting".
            chat_id:        Telegram 채팅방 ID.
            min_confidence: 이 값 미만 아이템 제외.

        Returns:
            AutoRegisterResult (등록 수, 오류 목록 등 포함).
        """
        effective_chat_id = chat_id if chat_id is not None else self._chat_id
        logger.info(
            f"[GoalTrackerClient] 보고 일괄 등록: type={report_type}, "
            f"len={len(report_text)}, chat_id={effective_chat_id}"
        )

        result = await auto_register_from_report(
            report_text=report_text,
            report_type=report_type,
            goal_tracker=self._tracker,
            registrar=self._registrar,
            state_machine=self._sm,
            chat_id=effective_chat_id,
            org_id=self._org_id,
            send_func=self._send,
            min_confidence=min_confidence,
        )

        logger.info(
            f"[GoalTrackerClient] 일괄 등록 완료: "
            f"found={result.action_items_found}, "
            f"registered={result.registered_count}, "
            f"errors={len(result.errors)}"
        )
        return result

    # ── 일괄 단건 등록 ────────────────────────────────────────────────────

    async def register_action_items_bulk(
        self,
        items: list[dict],
        source: str = "unknown",
        chat_id: Optional[int] = None,
    ) -> list[RegisterResult]:
        """조치사항 목록을 순차 등록. 개별 실패 시 에러 로깅 후 계속 처리.

        Args:
            items: [{"title": str, "assignee": str|None, "due_date": str|None, ...}]
            source: 출처 레이블.
            chat_id: Telegram 채팅방 ID.

        Returns:
            RegisterResult 리스트 (성공 + 실패 모두 포함).
        """
        results: list[RegisterResult] = []
        for item in items:
            try:
                r = await self.register_action_item(
                    title=item.get("title", ""),
                    assignee=item.get("assignee"),
                    due_date=item.get("due_date"),
                    source=source,
                    priority=item.get("priority", "medium"),
                    chat_id=chat_id,
                )
            except Exception as e:
                logger.error(
                    f"[GoalTrackerClient] 벌크 등록 아이템 실패: "
                    f"{item.get('title', '')[:40]} — {e}"
                )
                r = RegisterResult(
                    goal_id=None,
                    title=item.get("title", ""),
                    assignee=item.get("assignee"),
                    due_date=item.get("due_date"),
                    source=source,
                    success=False,
                    error=str(e),
                )
            results.append(r)

        success_count = sum(1 for r in results if r.success)
        logger.info(
            f"[GoalTrackerClient] 벌크 등록 완료: "
            f"{success_count}/{len(results)}개 성공"
        )
        return results

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────

    @staticmethod
    def _source_to_meeting_type(source: str) -> MeetingType:
        """source 문자열 → MeetingType enum 변환."""
        mapping = {
            "daily_retro": MeetingType.DAILY_RETRO,
            "일일회고": MeetingType.DAILY_RETRO,
            "weekly_meeting": MeetingType.WEEKLY_MEETING,
            "주간회의": MeetingType.WEEKLY_MEETING,
        }
        return mapping.get(source.lower(), MeetingType.UNKNOWN)

    # ── 상태 조회 ─────────────────────────────────────────────────────────

    @property
    def history(self) -> list[RegisterResult]:
        """등록 이력 (메모리 내)."""
        return list(self._history)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self._history if r.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self._history if not r.success)

    def clear_history(self) -> None:
        self._history.clear()

    def __repr__(self) -> str:
        return (
            f"<GoalTrackerClient org={self._org_id} "
            f"success={self.success_count} fail={self.failure_count}>"
        )


async def _noop_send(chat_id: int, text: str) -> None:  # pragma: no cover
    pass
