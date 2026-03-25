"""core/state_machine.py — 회의 종료 이벤트 기반 상태머신 진입점.

idle→evaluate→replan→dispatch 4단계 전이 로직의 core 레이어 진입점.

이 모듈은 두 가지 역할을 한다:
    1. goal_tracker.state_machine 의 핵심 클래스를 re-export (하위 호환)
    2. 회의 종료 이벤트 트리거 연결 — ``on_meeting_end(meeting_type, chat_log)``

상태 전이 흐름:
    ┌──────────────────────────────────────────────────────────────┐
    │ IDLE                                                         │
    │  ↓ on_meeting_end() 호출 → start_evaluate()                 │
    │ EVALUATE  — 액션아이템 존재 여부 판단                          │
    │  ↓ (아이템 있음) evaluate_complete 이벤트                     │
    │ REPLAN    — GoalTracker 기존 항목과 중복 체크 후 등록 대상 확정│
    │  ↓ (태스크 있음) replan_complete 이벤트                       │
    │ DISPATCH  — GoalTracker 등록 + MeetingLoopPipeline 실행       │
    │  ↓ dispatch_complete 이벤트                                   │
    │ IDLE      — 사이클 완료                                       │
    └──────────────────────────────────────────────────────────────┘

사용 예::

    # 단순 사용 — 진입점 함수
    result = await on_meeting_end(
        meeting_type="daily_retro",
        chat_log=retro_chat_text,
    )
    print(result.dispatched_count)  # dispatch된 태스크 수

    # 고급 사용 — 상태머신 직접 제어
    from core.state_machine import MeetingStateMachine
    sm = MeetingStateMachine(org_id="aiorg_pm_bot")
    await sm.on_meeting_end("weekly_meeting", chat_log)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from loguru import logger

# ── goal_tracker 핵심 클래스 re-export ────────────────────────────────────────
# 하위 호환: from core.state_machine import GoalTrackerStateMachine
from goal_tracker.state_machine import (  # noqa: F401
    EvaluationResult,
    GoalTrackerState,
    GoalTrackerStateMachine,
    InvalidTransitionError,
    StateMachineContext,
    StateTransition,
)
from goal_tracker.loop_runner import LoopRunResult, run_meeting_cycle
from tools.meeting_loop_pipeline import MeetingLoopPipeline
from tools.goaltracker_client import GoalTrackerClient


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 회의 종료 결과 ─────────────────────────────────────────────────────────────


@dataclass
class MeetingEndResult:
    """on_meeting_end() 실행 결과.

    Attributes:
        meeting_type:     처리한 회의 유형 ("daily_retro" | "weekly_meeting").
        states_visited:   거쳐간 상태 목록 (예: ["idle","evaluate","replan","dispatch","idle"]).
        action_items_found: parse 단계에서 추출된 조치사항 수.
        dispatched_count: GoalTracker에 실제 등록·dispatch된 수.
        registered_ids:   등록된 goal_id 목록.
        success:          오류 없이 완료했으면 True.
        error:            오류 메시지 (없으면 None).
        loop_result:      AutonomousLoopRunner 실행 결과 (상세 정보).
    """

    meeting_type: str
    states_visited: list[str] = field(default_factory=list)
    action_items_found: int = 0
    dispatched_count: int = 0
    registered_ids: list[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    loop_result: Optional[LoopRunResult] = None
    finished_at: Optional[datetime] = None

    def finish(self) -> "MeetingEndResult":
        self.finished_at = _utcnow()
        return self

    def __str__(self) -> str:
        return (
            f"MeetingEndResult("
            f"type={self.meeting_type}, "
            f"found={self.action_items_found}, "
            f"dispatched={self.dispatched_count}, "
            f"ok={self.success})"
        )


# ── 모듈 레벨 진입점 함수 ─────────────────────────────────────────────────────


async def on_meeting_end(
    meeting_type: str,
    chat_log: str,
    *,
    org_id: str = "aiorg_pm_bot",
    goal_tracker=None,
    state_machine: Optional[GoalTrackerStateMachine] = None,
    dispatch_func: Optional[Callable[[list[str]], Awaitable[None]]] = None,
    send_func: Optional[Callable[[int, str], Awaitable[None]]] = None,
    chat_id: int = 0,
    min_confidence: float = 0.5,
) -> MeetingEndResult:
    """회의 종료 이벤트 진입점 — 상태머신을 idle→evaluate로 전환하고 파이프라인 실행.

    일일회고 또는 주간회의 종료 시그널을 받아:
        1. MeetingLoopPipeline 으로 chat_log 파싱 + GoalTracker 등록
        2. GoalTrackerStateMachine 으로 idle→evaluate→replan→dispatch 전이
        3. dispatch 단계에서 담당 봇에게 알림 전송

    Args:
        meeting_type:  "daily_retro" | "weekly_meeting".
        chat_log:      회의 채팅 로그 전문.
        org_id:        요청 조직 ID (기본: "aiorg_pm_bot").
        goal_tracker:  GoalTracker 인스턴스 (없으면 dry-run).
        state_machine: 외부에서 주입된 GoalTrackerStateMachine.
                       None 이면 내부에서 신규 생성.
        dispatch_func: DISPATCH 단계 콜백.
        send_func:     Telegram 알림 전송 함수.
        chat_id:       Telegram 채팅방 ID.
        min_confidence: 파싱 최소 신뢰도.

    Returns:
        MeetingEndResult 인스턴스.

    Example::

        result = await on_meeting_end(
            meeting_type="daily_retro",
            chat_log=retro_text,
            goal_tracker=tracker,
            send_func=telegram_send,
            chat_id=CHAT_ID,
        )
        if result.dispatched_count > 0:
            print(f"{result.dispatched_count}개 조치사항 GoalTracker 등록 완료")
    """
    # MeetingStateMachine 인스턴스를 통해 처리 위임
    sm_wrapper = MeetingStateMachine(
        org_id=org_id,
        goal_tracker=goal_tracker,
        state_machine=state_machine,
        dispatch_func=dispatch_func,
        send_func=send_func,
        chat_id=chat_id,
        min_confidence=min_confidence,
    )
    return await sm_wrapper.on_meeting_end(meeting_type, chat_log)


# ── MeetingStateMachine ────────────────────────────────────────────────────────


class MeetingStateMachine:
    """회의 이벤트 기반 GoalTracker 상태머신 래퍼.

    MeetingLoopPipeline + GoalTrackerStateMachine + AutonomousLoopRunner 를
    통합하여 회의 종료 → GoalTracker 등록 → 상태 전이 흐름을 완성한다.

    상태 전이 흐름 주석:
        1. IDLE        : 초기 대기 상태. on_meeting_end() 호출 시 EVALUATE로 전이.
        2. EVALUATE    : 채팅 로그 파싱 결과 평가. 액션아이템 존재 여부 판단.
                         - 아이템 있음 → REPLAN
                         - 아이템 없음 → IDLE 복귀 (처리 불필요)
        3. REPLAN      : GoalTracker 기존 항목과 중복 체크 후 등록 대상 확정.
                         MeetingLoopPipeline.run() 호출하여 parse+extract+register 실행.
                         - 등록된 goal_id 있음 → DISPATCH
                         - 등록 없음 → IDLE 복귀
        4. DISPATCH    : AutonomousLoopRunner.run_cycle() 호출.
                         GoalTracker 등록 완료 + 담당 봇 알림 전송.
                         - 항상 IDLE 복귀 (성공/실패 무관)

    Args:
        org_id:        요청 조직 ID.
        goal_tracker:  GoalTracker 인스턴스.
        state_machine: 외부 주입 GoalTrackerStateMachine (None 이면 내부 생성).
        dispatch_func: DISPATCH 콜백.
        send_func:     Telegram 전송 함수.
        chat_id:       기본 Telegram 채팅방 ID.
        min_confidence: 파싱 최소 신뢰도.
    """

    def __init__(
        self,
        org_id: str = "aiorg_pm_bot",
        goal_tracker=None,
        state_machine: Optional[GoalTrackerStateMachine] = None,
        dispatch_func: Optional[Callable[[list[str]], Awaitable[None]]] = None,
        send_func: Optional[Callable[[int, str], Awaitable[None]]] = None,
        chat_id: int = 0,
        min_confidence: float = 0.5,
    ) -> None:
        self._org_id = org_id
        self._tracker = goal_tracker
        self._send = send_func or _noop_send
        self._chat_id = chat_id
        self._min_confidence = min_confidence
        self._dispatch_func = dispatch_func or _noop_dispatch

        # 외부 주입 또는 내부 생성 (goal_id는 실행 시점에 결정)
        self._external_sm = state_machine

        # 최근 실행 결과 (상태 조회용)
        self._last_result: Optional[MeetingEndResult] = None

    # ── 메인 진입점 ────────────────────────────────────────────────────────

    async def on_meeting_end(
        self,
        meeting_type: str,
        chat_log: str,
        chat_id: Optional[int] = None,
    ) -> MeetingEndResult:
        """회의 종료 이벤트 처리 — idle→evaluate→replan→dispatch 전이 실행.

        Args:
            meeting_type: "daily_retro" | "weekly_meeting".
            chat_log:     회의 채팅 로그 전문.
            chat_id:      Telegram 채팅방 ID (None 이면 인스턴스 기본값 사용).

        Returns:
            MeetingEndResult 인스턴스.
        """
        effective_chat_id = chat_id if chat_id is not None else self._chat_id
        logger.info(
            f"[MeetingStateMachine] on_meeting_end 시작 — "
            f"type={meeting_type}, log_len={len(chat_log)}"
        )

        result = MeetingEndResult(meeting_type=meeting_type)

        try:
            result = await self._execute(meeting_type, chat_log, effective_chat_id, result)
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"[MeetingStateMachine] 실행 오류: {e}")

        result.finish()
        self._last_result = result
        logger.info(f"[MeetingStateMachine] 완료 — {result}")
        return result

    # ── 내부 실행 ─────────────────────────────────────────────────────────

    async def _execute(
        self,
        meeting_type: str,
        chat_log: str,
        chat_id: int,
        result: MeetingEndResult,
    ) -> MeetingEndResult:
        """idle→evaluate→replan→dispatch 전체 흐름 실행."""
        from datetime import date

        # ── Step 1 (IDLE → EVALUATE): 채팅 로그 파싱 ───────────────────────
        result.states_visited.append("idle")
        logger.info("[MeetingStateMachine] IDLE → EVALUATE: 채팅 로그 파싱 시작")

        # MeetingLoopPipeline 사용하여 parse + extract + register
        # (모듈 레벨 import 사용 — mock patch 가능)

        client = GoalTrackerClient(
            org_id=self._org_id,
            goal_tracker=self._tracker,
            send_func=self._send,
            chat_id=chat_id,
        )
        pipeline = MeetingLoopPipeline(
            client=client,
            min_confidence=self._min_confidence,
        )

        # ── EVALUATE: 파싱 결과 평가 ────────────────────────────────────────
        result.states_visited.append("evaluate")
        pipeline_result = await pipeline.run(
            chat_log=chat_log,
            meeting_type=meeting_type,
            chat_id=chat_id,
        )
        result.action_items_found = pipeline_result.parsed_count

        logger.info(
            f"[MeetingStateMachine] EVALUATE 완료 — "
            f"추출={pipeline_result.parsed_count}, "
            f"등록 대상={pipeline_result.extracted_count}"
        )

        # 액션아이템 없음 → IDLE 복귀
        if pipeline_result.parsed_count == 0:
            result.states_visited.append("idle")
            logger.info(
                "[MeetingStateMachine] EVALUATE → IDLE: 조치사항 없음, 파이프라인 종료"
            )
            return result

        # ── REPLAN: 중복 체크 완료, 등록 대상 확정 ──────────────────────────
        result.states_visited.append("replan")
        registered_ids = pipeline_result.registered_ids
        logger.info(
            f"[MeetingStateMachine] REPLAN 완료 — "
            f"등록={pipeline_result.registered_count}, "
            f"실패={pipeline_result.failed_count}"
        )

        # 등록된 태스크 없음 → IDLE 복귀
        if not registered_ids:
            result.states_visited.append("idle")
            logger.info(
                "[MeetingStateMachine] REPLAN → IDLE: "
                "등록된 태스크 없음 (모두 중복 또는 실패)"
            )
            return result

        # ── DISPATCH: GoalTracker 등록 + 상태머신 사이클 실행 ───────────────
        result.states_visited.append("dispatch")
        goal_id = f"G-{meeting_type}-{date.today().isoformat()}"

        # GoalTrackerStateMachine 사용하여 dispatch 사이클 실행
        sm = self._external_sm or GoalTrackerStateMachine(
            goal_id=goal_id,
            max_iterations=1,  # 회의 1회분 → 1사이클만 실행
        )

        loop_result = await run_meeting_cycle(
            meeting_type=meeting_type,
            registered_ids=registered_ids,
            dispatch_func=self._dispatch_func,
        )

        result.loop_result = loop_result
        result.registered_ids = registered_ids
        result.dispatched_count = loop_result.dispatched_count if loop_result.dispatched else 0

        # DISPATCH → IDLE
        result.states_visited.append("idle")

        # 상태머신 로그 기록
        logger.info(
            f"[MeetingStateMachine] DISPATCH 완료 — "
            f"dispatched={loop_result.dispatched_count}개, "
            f"states={loop_result.states_visited}"
        )

        # 완료 알림 전송
        if chat_id and self._send is not _noop_send:
            await self._send_completion_notice(chat_id, meeting_type, result)

        return result

    async def _send_completion_notice(
        self,
        chat_id: int,
        meeting_type: str,
        result: MeetingEndResult,
    ) -> None:
        """GoalTracker 등록 완료 알림 전송."""
        type_label = {
            "daily_retro": "일일회고",
            "weekly_meeting": "주간회의",
        }.get(meeting_type, "회의")

        msg = (
            f"✅ **{type_label}** GoalTracker 자동 등록 완료\n"
            f"  조치사항 추출: **{result.action_items_found}개**\n"
            f"  GoalTracker 등록: **{result.dispatched_count}개**\n"
            f"  상태 전이: {' → '.join(result.states_visited)}"
        )
        try:
            await self._send(chat_id, msg)
        except Exception as e:
            logger.warning(f"[MeetingStateMachine] 완료 알림 실패 (비치명): {e}")

    # ── 상태 조회 ─────────────────────────────────────────────────────────

    @property
    def last_result(self) -> Optional[MeetingEndResult]:
        return self._last_result

    def __repr__(self) -> str:
        return f"<MeetingStateMachine org={self._org_id}>"


async def _noop_send(chat_id: int, text: str) -> None:  # pragma: no cover
    pass


async def _noop_dispatch(task_ids: list[str]) -> None:  # pragma: no cover
    for t in task_ids:
        logger.info(f"[MeetingStateMachine] dispatch (noop): {t}")
