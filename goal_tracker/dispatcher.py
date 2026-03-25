"""GoalTracker dispatch 라우팅 모듈 — 부서별 태스크 자동 배분.

GoalTrackerDispatcher는 상태머신의 REPLAN→DISPATCH 전이 시 실행된다:
    1. 서브태스크에 assigned_dept 미지정 시 DeptRouter로 자동 라우팅
    2. 라우팅 계획 로깅 및 사용자 알림
    3. PMOrchestrator.dispatch() 호출로 실제 배분 실행
    4. 상태머신에 dispatch 결과 주입 (start_dispatch)

의존성:
    goal_tracker.router.DeptRouter
    goal_tracker.state_machine.GoalTrackerStateMachine
    core.pm_orchestrator.SubTask (lazy import — 런타임에만 필요)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable

from loguru import logger

from goal_tracker.router import DeptRouter
from goal_tracker.state_machine import GoalTrackerState, GoalTrackerStateMachine


@dataclass
class DispatchResult:
    """dispatch 실행 결과."""

    goal_id: str
    dispatched_count: int
    task_ids: list[str]
    routing_summary: dict[str, list[str]] = field(default_factory=dict)
    # {org_id: [task_description[:50], ...]}
    errors: list[str] = field(default_factory=list)
    success: bool = True

    def __post_init__(self) -> None:
        self.success = len(self.errors) == 0 and self.dispatched_count > 0


@dataclass
class RoutingPlan:
    """dispatch 전 미리보기 (dry-run 결과)."""

    goal_id: str
    plan: dict[str, list[dict]]  # {org_id: [subtask_dict]}
    total_tasks: int
    dept_count: int

    @classmethod
    def from_plan(cls, goal_id: str, plan: dict[str, list[dict]]) -> "RoutingPlan":
        total = sum(len(v) for v in plan.values())
        return cls(
            goal_id=goal_id,
            plan=plan,
            total_tasks=total,
            dept_count=len(plan),
        )

    def to_summary_text(self) -> str:
        lines = [f"📋 라우팅 계획 ({self.total_tasks}개 태스크, {self.dept_count}개 부서):"]
        for org_id, tasks in self.plan.items():
            lines.append(f"  • {org_id}: {len(tasks)}개")
            for t in tasks[:3]:
                lines.append(f"    - {t.get('description', '')[:60]}")
        return "\n".join(lines)


class GoalTrackerDispatcher:
    """GoalTracker DISPATCH 단계 실행 모듈.

    사용 예::

        dispatcher = GoalTrackerDispatcher(router=DeptRouter())
        result = await dispatcher.dispatch_goal(
            state_machine=sm,
            subtasks=subtask_list,
            chat_id=chat_id,
            dispatch_fn=orchestrator.dispatch,
        )
    """

    def __init__(
        self,
        router: DeptRouter | None = None,
        send_func: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> None:
        self._router = router or DeptRouter()
        self._send: Callable[[int, str], Awaitable[None]] = send_func or _noop_send

    # ── 메인 dispatch ─────────────────────────────────────────────────────

    async def dispatch_goal(
        self,
        state_machine: GoalTrackerStateMachine,
        subtasks: list[dict],
        chat_id: int,
        dispatch_fn: Callable[..., Awaitable[list[str]]],
    ) -> DispatchResult:
        """서브태스크를 부서별로 라우팅하여 배분.

        Args:
            state_machine: 현재 목표의 상태머신 인스턴스 (REPLAN 상태여야 함).
            subtasks: [{"description": str, "assigned_dept": str | None}] 형식.
            chat_id: Telegram 채팅방 ID.
            dispatch_fn: 실제 배분 함수 (PMOrchestrator.dispatch 호환).
                signature: async (parent_id, subtask_objs, chat_id) -> list[str]

        Returns:
            DispatchResult 인스턴스.
        """
        goal_id = state_machine.goal_id

        if state_machine.state != GoalTrackerState.REPLAN:
            err = f"dispatch_goal 호출 오류: REPLAN 상태 아님 (현재: {state_machine.state})"
            logger.error(f"[Dispatcher:{goal_id}] {err}")
            return DispatchResult(
                goal_id=goal_id,
                dispatched_count=0,
                task_ids=[],
                errors=[err],
            )

        # 1. 라우팅 계획 수립
        enriched, routing_summary = self._enrich_subtasks(subtasks)

        logger.info(
            f"[Dispatcher:{goal_id}] dispatch 시작: {len(enriched)}개 태스크, "
            f"부서: {list(routing_summary.keys())}"
        )

        # 2. SubTask 객체 생성 및 dispatch 실행
        try:
            subtask_objs = self._to_subtask_objects(enriched)
            task_ids = await dispatch_fn(goal_id, subtask_objs, chat_id)
        except Exception as e:
            err = f"dispatch 실패: {e}"
            logger.error(f"[Dispatcher:{goal_id}] {err}")
            return DispatchResult(
                goal_id=goal_id,
                dispatched_count=0,
                task_ids=[],
                routing_summary=routing_summary,
                errors=[err],
            )

        result = DispatchResult(
            goal_id=goal_id,
            dispatched_count=len(task_ids),
            task_ids=task_ids,
            routing_summary=routing_summary,
            errors=[] if task_ids else ["dispatch 태스크 없음"],
        )

        # 3. 상태머신 DISPATCH 전이
        if task_ids:
            state_machine.start_dispatch(task_ids)
            await self._notify_dispatch(chat_id, goal_id, routing_summary, len(task_ids))
        else:
            logger.warning(f"[Dispatcher:{goal_id}] dispatch 태스크 없음")

        return result

    # ── dry-run ───────────────────────────────────────────────────────────

    def plan_routing(
        self,
        goal_id: str,
        subtasks: list[dict],
    ) -> RoutingPlan:
        """dispatch 실행 전 라우팅 계획 미리보기.

        Args:
            goal_id: 목표 ID (로깅용).
            subtasks: 서브태스크 목록.

        Returns:
            RoutingPlan (dry-run 결과).
        """
        plan = self._router.plan(subtasks)
        routing_plan = RoutingPlan.from_plan(goal_id, plan)
        logger.debug(
            f"[Dispatcher:{goal_id}] 라우팅 계획:\n{routing_plan.to_summary_text()}"
        )
        return routing_plan

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────

    def _enrich_subtasks(
        self,
        subtasks: list[dict],
    ) -> tuple[list[dict], dict[str, list[str]]]:
        """assigned_dept 미지정 서브태스크에 라우터 적용.

        Returns:
            (enriched_subtasks, routing_summary)
            routing_summary: {org_id: [description[:50], ...]}
        """
        enriched: list[dict] = []
        routing_summary: dict[str, list[str]] = {}

        for st in subtasks:
            desc = st.get("description", "")
            dept = st.get("assigned_dept") or self._router.route(desc)
            enriched_st = {**st, "assigned_dept": dept}
            enriched.append(enriched_st)
            routing_summary.setdefault(dept, []).append(desc[:50])

        return enriched, routing_summary

    @staticmethod
    def _to_subtask_objects(enriched: list[dict]) -> list:
        """dict 리스트 → SubTask 객체 리스트 변환.

        core.pm_orchestrator.SubTask를 lazy import하여 의존성 순환 방지.
        """
        try:
            from core.pm_orchestrator import SubTask
        except ImportError:
            # 테스트 환경 등에서 core가 없을 경우 — dict 그대로 반환
            return enriched  # type: ignore[return-value]

        return [
            SubTask(
                description=st.get("description", ""),
                assigned_dept=st.get("assigned_dept", "aiorg_product_bot"),
            )
            for st in enriched
        ]

    async def _notify_dispatch(
        self,
        chat_id: int,
        goal_id: str,
        routing_summary: dict[str, list[str]],
        total: int,
    ) -> None:
        """dispatch 완료 사용자 알림."""
        summary_lines = [
            f"  {self._router.get_dept_name(dept)} ({dept}): {len(tasks)}개"
            for dept, tasks in routing_summary.items()
        ]
        msg = (
            f"📤 **{goal_id}** dispatch 완료: **{total}개** 태스크\n"
            + "\n".join(summary_lines)
        )
        try:
            await self._send(chat_id, msg)
        except Exception as e:
            logger.warning(f"[Dispatcher:{goal_id}] 알림 전송 실패: {e}")


async def _noop_send(chat_id: int, text: str) -> None:  # pragma: no cover
    pass
