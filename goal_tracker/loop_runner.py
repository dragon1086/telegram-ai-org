"""AutonomousLoopRunner — GoalTrackerStateMachine 기반 단일 사이클 실행기.

일일회고/주간회의 종료 후 auto_register_from_report()로 등록된 goal_id 목록을
받아 idle→evaluate→replan→dispatch 한 사이클을 실행한다.

AutonomousLoop(core.autonomous_loop)가 장기 실행 백그라운드 루프라면,
AutonomousLoopRunner는 회의 1회 분량의 조치사항을 즉시 한 사이클 처리하는
경량 실행기다.

사용 예::

    runner = AutonomousLoopRunner(goal_id="G-meeting-001")
    result = await runner.run_cycle(registered_ids=["G-pm-001", "G-pm-002"])
    print(result.states_visited)  # ["idle", "evaluate", "replan", "dispatch", "idle"]

dispatch_func 주입 예::

    async def my_dispatch(task_ids: list[str]) -> None:
        for t in task_ids:
            await send_telegram(f"📬 dispatch: {t}")

    runner = AutonomousLoopRunner(
        goal_id="G-meeting-001",
        dispatch_func=my_dispatch,
    )
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from loguru import logger

from goal_tracker.action_parser import ActionItem
from goal_tracker.router import DeptRouter
from goal_tracker.state_machine import (
    EvaluationResult,
    GoalTrackerState,
    GoalTrackerStateMachine,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 결과 데이터클래스 ─────────────────────────────────────────────────────────


@dataclass
class DispatchRecord:
    """dispatch 단계 배분 기록."""

    task_id: str
    assigned_dept: str
    description: str = ""
    dispatched_at: datetime = field(default_factory=_utcnow)


@dataclass
class LoopRunResult:
    """AutonomousLoopRunner.run_cycle() 실행 결과."""

    goal_id: str
    states_visited: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    dispatched: bool = False
    dispatch_records: list[DispatchRecord] = field(default_factory=list)
    error: Optional[str] = None
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None
    iteration: int = 0

    @property
    def success(self) -> bool:
        """오류 없이 완료했으면 True."""
        return self.error is None

    @property
    def dispatched_count(self) -> int:
        return len(self.dispatch_records)

    def finish(self) -> "LoopRunResult":
        self.finished_at = _utcnow()
        return self

    def __str__(self) -> str:
        return (
            f"LoopRunResult(goal={self.goal_id}, "
            f"states={self.states_visited}, "
            f"dispatched={self.dispatched_count}, "
            f"ok={self.success})"
        )


# ── 기본 핸들러 ───────────────────────────────────────────────────────────────


async def _noop_dispatch(task_ids: list[str]) -> None:  # pragma: no cover
    """기본 dispatch 핸들러 — 로그만 남김."""
    for t in task_ids:
        logger.info(f"[LoopRunner] dispatch (noop): {t}")


# ── AutonomousLoopRunner ──────────────────────────────────────────────────────


class AutonomousLoopRunner:
    """GoalTrackerStateMachine을 사용하는 단일 사이클 자율 루프 실행기.

    회의 종료 후 등록된 goal_id 목록을 받아
    idle→evaluate→replan→dispatch→idle 한 사이클을 실행한다.

    Args:
        goal_id:        이 사이클을 대표하는 목표 ID.
        state_machine:  외부에서 주입된 GoalTrackerStateMachine.
                        None이면 자동 생성 (goal_id 기반).
        router:         부서 라우팅 (None이면 DeptRouter() 기본값).
        dispatch_func:  DISPATCH 단계에서 호출할 콜백.
                        ``async def dispatch_func(task_ids: list[str]) -> None``
        on_dispatch_complete:
                        DISPATCH → IDLE 전이 직후 호출되는 확인 콜백.
                        ``async def on_dispatch_complete(result: LoopRunResult) -> None``
                        dispatch 결과를 수신하여 후속 처리(알림·DB 갱신 등)에 활용한다.
        max_iterations: GoalTrackerStateMachine max_iterations.
        max_stagnation: GoalTrackerStateMachine max_stagnation.
    """

    def __init__(
        self,
        goal_id: str,
        *,
        state_machine: Optional[GoalTrackerStateMachine] = None,
        router: Optional[DeptRouter] = None,
        dispatch_func: Optional[Callable[[list[str]], Awaitable[None]]] = None,
        on_dispatch_complete: Optional[Callable[["LoopRunResult"], Awaitable[None]]] = None,
        max_iterations: int = 10,
        max_stagnation: int = 3,
    ) -> None:
        self._goal_id = goal_id
        self._sm = state_machine or GoalTrackerStateMachine(
            goal_id=goal_id,
            max_iterations=max_iterations,
            max_stagnation=max_stagnation,
        )
        self._router = router or DeptRouter()
        self._dispatch_func = dispatch_func or _noop_dispatch
        self._on_dispatch_complete = on_dispatch_complete

    # ── 프로퍼티 ───────────────────────────────────────────────────────────

    @property
    def state_machine(self) -> GoalTrackerStateMachine:
        return self._sm

    @property
    def current_state(self) -> GoalTrackerState:
        return self._sm.state

    # ── 메인 진입점 ────────────────────────────────────────────────────────

    async def run_cycle(
        self,
        registered_ids: list[str],
        action_items: Optional[list[ActionItem]] = None,
        on_dispatch_complete: Optional[Callable[["LoopRunResult"], Awaitable[None]]] = None,
    ) -> LoopRunResult:
        """idle→evaluate→replan→dispatch→idle 한 사이클 실행.

        Args:
            registered_ids:       auto_register_from_report()로 반환된 goal_id 목록.
            action_items:         파싱된 ActionItem 목록 (라우팅 힌트용, 없으면 ID만 사용).
            on_dispatch_complete: DISPATCH 완료 후 호출될 확인 콜백.
                                  생성자의 on_dispatch_complete보다 우선 적용된다.
                                  ``async def callback(result: LoopRunResult) -> None``

        Returns:
            LoopRunResult 인스턴스.
        """
        # 호출 시점 콜백이 있으면 생성자 콜백보다 우선
        confirm_callback = on_dispatch_complete or self._on_dispatch_complete

        result = LoopRunResult(goal_id=self._goal_id)
        logger.info(
            f"[LoopRunner:{self._goal_id}] 사이클 시작 — "
            f"{len(registered_ids)}개 등록 goal_id"
        )

        try:
            result = await self._run_full_cycle(result, registered_ids, action_items or [])
        except Exception as e:
            result.error = str(e)
            logger.error(f"[LoopRunner:{self._goal_id}] 사이클 오류: {e}")
            # 오류 시 IDLE 복귀 시도
            if self._sm.state != GoalTrackerState.IDLE:
                self._sm.return_to_idle(f"오류 복귀: {e}")
                result.states_visited.append("idle")

        result.finish()

        # dispatch 확인 콜백 실행 (dispatch 성공 시에만)
        if confirm_callback is not None and result.dispatched:
            try:
                await confirm_callback(result)
                logger.info(
                    f"[LoopRunner:{self._goal_id}] dispatch 확인 콜백 완료 "
                    f"— dispatched={result.dispatched_count}개"
                )
            except Exception as cb_err:
                logger.warning(
                    f"[LoopRunner:{self._goal_id}] dispatch 확인 콜백 오류 "
                    f"(비치명적): {cb_err}"
                )

        return result

    # ── 내부 사이클 단계 ──────────────────────────────────────────────────

    async def _run_full_cycle(
        self,
        result: LoopRunResult,
        registered_ids: list[str],
        action_items: list[ActionItem],
    ) -> LoopRunResult:
        """IDLE → EVALUATE → REPLAN → DISPATCH → IDLE 순서 실행."""
        result.states_visited.append("idle")

        # ── IDLE → EVALUATE ───────────────────────────────────────────────
        if not self._sm.start_evaluate():
            reason = self._sm.terminal_reason() or "EVALUATE 진입 불가"
            logger.warning(f"[LoopRunner:{self._goal_id}] {reason}")
            result.error = reason
            return result

        result.states_visited.append("evaluate")
        logger.info(f"[LoopRunner:{self._goal_id}] EVALUATE — {len(registered_ids)}개 태스크 평가")

        # ── EVALUATE 수행 ─────────────────────────────────────────────────
        evaluation = self._build_evaluation(registered_ids)
        result.iteration = self._sm.ctx.iteration

        # EVALUATE → REPLAN or IDLE
        transitioned = self._sm.transition("evaluate_complete", evaluation=evaluation)
        if not transitioned:
            result.states_visited.append("idle")
            return result

        if self._sm.state != GoalTrackerState.REPLAN:
            result.states_visited.append("idle")
            return result

        result.states_visited.append("replan")
        logger.info(f"[LoopRunner:{self._goal_id}] REPLAN — 태스크 라우팅 중")

        # ── REPLAN 수행 ────────────────────────────────────────────────────
        task_ids = self._build_task_ids(registered_ids, action_items)
        result.task_ids = task_ids

        # REPLAN → DISPATCH or IDLE
        self._sm.transition("replan_complete", task_ids=task_ids)

        if self._sm.state != GoalTrackerState.DISPATCH:
            result.states_visited.append("idle")
            return result

        result.states_visited.append("dispatch")
        logger.info(
            f"[LoopRunner:{self._goal_id}] DISPATCH — {len(task_ids)}개 태스크 배분"
        )

        # ── DISPATCH 수행 ──────────────────────────────────────────────────
        dispatch_records = await self._do_dispatch(task_ids, action_items)
        result.dispatch_records = dispatch_records
        result.dispatched = True

        # DISPATCH → IDLE
        self._sm.transition("dispatch_complete", reason="dispatch 완료")
        result.states_visited.append("idle")

        logger.info(
            f"[LoopRunner:{self._goal_id}] 사이클 완료 — "
            f"states={result.states_visited}, dispatched={len(dispatch_records)}개"
        )
        return result

    # ── 평가 로직 ─────────────────────────────────────────────────────────

    def _build_evaluation(self, registered_ids: list[str]) -> EvaluationResult:
        """등록된 task_id 목록 기반 EvaluationResult 생성.

        회의 직후 첫 번째 사이클에서는 항상 미달성(achieved=False)으로 평가해
        REPLAN → DISPATCH 사이클을 강제로 실행한다.
        """
        total = len(registered_ids)
        if total == 0:
            # 등록된 태스크 없음 → 달성 처리 (아무것도 할 일 없음)
            logger.info(f"[LoopRunner:{self._goal_id}] 등록 태스크 없음 → 즉시 달성 처리")
            return EvaluationResult(
                achieved=True,
                progress_pct=1.0,
                done_count=0,
                total_count=0,
                confidence=1.0,
            )

        # 첫 사이클: dispatch할 태스크가 있으므로 미달성 처리
        return EvaluationResult(
            achieved=False,
            progress_pct=0.0,
            done_count=0,
            total_count=total,
            remaining_work=f"{total}개 조치사항 dispatch 대기",
            confidence=0.0,
        )

    def _build_task_ids(
        self,
        registered_ids: list[str],
        action_items: list[ActionItem],
    ) -> list[str]:
        """REPLAN 단계에서 dispatch 대상 task_id 목록 생성.

        registered_ids를 그대로 사용하며, 라우팅 정보를 메타데이터에 보강한다.
        """
        return list(registered_ids)

    # ── dispatch 실행 ─────────────────────────────────────────────────────

    async def _do_dispatch(
        self,
        task_ids: list[str],
        action_items: list[ActionItem],
    ) -> list[DispatchRecord]:
        """dispatch_func 호출 및 DispatchRecord 생성."""
        records: list[DispatchRecord] = []

        # action_items 있으면 담당 부서 결정 지원
        dept_map: dict[int, str] = {}
        for i, item in enumerate(action_items):
            if i < len(task_ids):
                dept = item.assigned_dept or self._router.route(item.description)
                dept_map[i] = dept

        for i, task_id in enumerate(task_ids):
            dept = dept_map.get(i, "")
            rec = DispatchRecord(
                task_id=task_id,
                assigned_dept=dept,
                description=(
                    action_items[i].description[:80]
                    if i < len(action_items) else ""
                ),
            )
            records.append(rec)
            logger.info(
                f"[LoopRunner:{self._goal_id}] dispatch → "
                f"{task_id} (담당: {dept or '미지정'})"
            )

        # dispatch 콜백 호출
        try:
            await self._dispatch_func(task_ids)
        except Exception as e:
            logger.error(f"[LoopRunner:{self._goal_id}] dispatch_func 오류: {e}")
            raise

        return records

    def __repr__(self) -> str:
        return (
            f"<AutonomousLoopRunner goal={self._goal_id} "
            f"state={self._sm.state.value}>"
        )


# ── 편의 함수 ─────────────────────────────────────────────────────────────────


async def run_meeting_cycle(
    meeting_type: str,
    registered_ids: list[str],
    action_items: Optional[list[ActionItem]] = None,
    dispatch_func: Optional[Callable[[list[str]], Awaitable[None]]] = None,
    on_dispatch_complete: Optional[Callable[["LoopRunResult"], Awaitable[None]]] = None,
) -> LoopRunResult:
    """회의 결과 GoalTracker 사이클 실행 편의 함수.

    Args:
        meeting_type:         "daily_retro" | "weekly_meeting".
        registered_ids:       auto_register_from_report() 반환 goal_id 목록.
        action_items:         파싱된 ActionItem 목록 (라우팅 힌트).
        dispatch_func:        DISPATCH 콜백.
        on_dispatch_complete: DISPATCH 완료 후 확인 콜백.
                              ``async def callback(result: LoopRunResult) -> None``

    Returns:
        LoopRunResult 인스턴스.

    Example::

        result = await run_meeting_cycle(
            meeting_type="daily_retro",
            registered_ids=["G-pm-001", "G-pm-002"],
        )
        assert result.dispatched
    """
    from datetime import date
    goal_id = f"G-{meeting_type}-{date.today().isoformat()}"

    runner = AutonomousLoopRunner(
        goal_id=goal_id,
        dispatch_func=dispatch_func,
    )
    return await runner.run_cycle(
        registered_ids=registered_ids,
        action_items=action_items,
        on_dispatch_complete=on_dispatch_complete,
    )
