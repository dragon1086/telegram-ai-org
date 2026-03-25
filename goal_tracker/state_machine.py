"""GoalTracker 상태머신 — idle→evaluate→replan→dispatch 4단계 전이 로직.

상태 정의:
    IDLE     → 대기. 활성 목표가 없거나 다음 사이클까지 슬립.
    EVALUATE → 현재 목표 달성률·마감일·블로커 분석.
    REPLAN   → 우선순위 재정렬 및 태스크 재배분 계획 수립.
    DISPATCH → 부서별 라우팅 테이블 기반 태스크 자동 배분.

전이 규칙:
    IDLE     → EVALUATE : can_enter_evaluate() — 활성 목표 존재 + 반복 한도 미초과
    EVALUATE → REPLAN   : can_enter_replan()   — 목표 미달성 + 정체 미감지
    EVALUATE → IDLE     : 목표 달성 or 정체 감지 시
    REPLAN   → DISPATCH : can_enter_dispatch() — 재계획 태스크 1개 이상
    REPLAN   → IDLE     : 재계획 태스크 없음 시
    DISPATCH → IDLE     : dispatch 완료 후 항상 IDLE 복귀
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    """timezone-aware UTC datetime (Python 3.14+ 호환)."""
    return datetime.now(timezone.utc)

from loguru import logger


class GoalTrackerState(str, Enum):
    """GoalTracker 4단계 상태."""

    IDLE = "idle"
    EVALUATE = "evaluate"
    REPLAN = "replan"
    DISPATCH = "dispatch"


@dataclass
class StateTransition:
    """상태 전이 기록."""

    from_state: GoalTrackerState
    to_state: GoalTrackerState
    trigger: str
    timestamp: datetime = field(default_factory=_utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """EVALUATE 단계 분석 결과."""

    achieved: bool
    progress_pct: float          # 0.0~1.0
    done_count: int
    total_count: int
    blocker: str = ""            # 현재 블로커 설명
    remaining_work: str = ""
    confidence: float = 0.0


@dataclass
class StateMachineContext:
    """상태머신 실행 컨텍스트."""

    goal_id: str
    current_state: GoalTrackerState = GoalTrackerState.IDLE
    iteration: int = 0
    max_iterations: int = 10
    stagnation_count: int = 0
    max_stagnation: int = 3
    last_evaluation: Optional[EvaluationResult] = None
    dispatched_task_ids: list = field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    history: list = field(default_factory=list)  # list[StateTransition]


class InvalidTransitionError(Exception):
    """허용되지 않는 상태 전이 시도."""
    pass


class GoalTrackerStateMachine:
    """idle→evaluate→replan→dispatch 명시적 상태머신.

    core.autonomous_loop.AutonomousLoop 의 _tick() 로직을 상태머신 패턴으로
    명시화한 클래스. GoalTracker 인스턴스와 독립적으로 상태를 관리한다.

    사용 예::

        sm = GoalTrackerStateMachine("G-pm-001", max_iterations=5)
        sm.start_evaluate()       # IDLE → EVALUATE
        sm.start_replan(eval_result)  # EVALUATE → REPLAN (미달성 시)
        sm.start_dispatch(task_ids)   # REPLAN → DISPATCH
        sm.return_to_idle("dispatch 완료")  # DISPATCH → IDLE
    """

    # 허용된 상태 전이 테이블
    VALID_TRANSITIONS: dict[GoalTrackerState, list[GoalTrackerState]] = {
        GoalTrackerState.IDLE:     [GoalTrackerState.EVALUATE],
        GoalTrackerState.EVALUATE: [GoalTrackerState.REPLAN, GoalTrackerState.IDLE],
        GoalTrackerState.REPLAN:   [GoalTrackerState.DISPATCH, GoalTrackerState.IDLE],
        GoalTrackerState.DISPATCH: [GoalTrackerState.IDLE],
    }

    def __init__(
        self,
        goal_id: str,
        max_iterations: int = 10,
        max_stagnation: int = 3,
    ) -> None:
        self.ctx = StateMachineContext(
            goal_id=goal_id,
            max_iterations=max_iterations,
            max_stagnation=max_stagnation,
        )

    # ── 상태 조회 ─────────────────────────────────────────────────────────

    @property
    def state(self) -> GoalTrackerState:
        return self.ctx.current_state

    @property
    def goal_id(self) -> str:
        return self.ctx.goal_id

    def can_transition(self, to_state: GoalTrackerState) -> bool:
        """현재 상태에서 to_state로 전이 가능한지 확인."""
        valid = self.VALID_TRANSITIONS.get(self.ctx.current_state, [])
        return to_state in valid

    # ── 진입 조건 ─────────────────────────────────────────────────────────

    def can_enter_evaluate(self) -> bool:
        """IDLE → EVALUATE 진입 조건.

        조건:
            - 현재 IDLE 상태
            - iteration < max_iterations (반복 한도 미초과)
            - stagnation < max_stagnation (정체 미감지)
        """
        if self.ctx.current_state != GoalTrackerState.IDLE:
            return False
        if self.ctx.iteration >= self.ctx.max_iterations:
            return False
        if self.ctx.stagnation_count >= self.ctx.max_stagnation:
            return False
        return True

    def can_enter_replan(self, evaluation: EvaluationResult) -> bool:
        """EVALUATE → REPLAN 진입 조건.

        조건:
            - 현재 EVALUATE 상태
            - 목표 미달성 (achieved=False)
            - 정체 미감지 (stagnation < max_stagnation)
        """
        if self.ctx.current_state != GoalTrackerState.EVALUATE:
            return False
        if evaluation.achieved:
            return False  # 달성됨 → IDLE 복귀
        if self.ctx.stagnation_count >= self.ctx.max_stagnation:
            return False  # 정체 → IDLE 복귀 (사용자 개입 필요)
        return True

    def can_enter_dispatch(self, task_count: int) -> bool:
        """REPLAN → DISPATCH 진입 조건.

        조건:
            - 현재 REPLAN 상태
            - 재계획 태스크 1개 이상
        """
        if self.ctx.current_state != GoalTrackerState.REPLAN:
            return False
        return task_count > 0

    # ── 상태 전이 메서드 ──────────────────────────────────────────────────

    def _do_transition(
        self,
        to_state: GoalTrackerState,
        trigger: str,
        metadata: dict | None = None,
    ) -> bool:
        """내부 상태 전이 실행. 이력 기록 포함."""
        if not self.can_transition(to_state):
            logger.warning(
                f"[SM:{self.ctx.goal_id}] 전이 불가: "
                f"{self.ctx.current_state} → {to_state} (trigger={trigger})"
            )
            return False

        transition = StateTransition(
            from_state=self.ctx.current_state,
            to_state=to_state,
            trigger=trigger,
            metadata=metadata or {},
        )
        self.ctx.history.append(transition)
        self.ctx.current_state = to_state
        self.ctx.updated_at = _utcnow()

        logger.info(
            f"[SM:{self.ctx.goal_id}] {transition.from_state} → {to_state} "
            f"(trigger={trigger}, iter={self.ctx.iteration}/{self.ctx.max_iterations})"
        )
        return True

    def start_evaluate(self) -> bool:
        """IDLE → EVALUATE 전이.

        Returns:
            True if 전이 성공, False if 진입 조건 미충족.
        """
        if not self.can_enter_evaluate():
            logger.debug(
                f"[SM:{self.ctx.goal_id}] EVALUATE 진입 불가 "
                f"(iter={self.ctx.iteration}/{self.ctx.max_iterations}, "
                f"stagnation={self.ctx.stagnation_count}/{self.ctx.max_stagnation})"
            )
            return False
        return self._do_transition(GoalTrackerState.EVALUATE, "목표 평가 시작")

    def start_replan(self, evaluation: EvaluationResult) -> bool:
        """EVALUATE → REPLAN 전이.

        iteration 카운터를 1 증가시키고 평가 결과를 컨텍스트에 저장한다.

        Returns:
            True if 전이 성공 (재계획 필요), False if 목표 달성 또는 정체.
        """
        if not self.can_enter_replan(evaluation):
            reason = "목표 달성" if evaluation.achieved else "정체 감지"
            logger.info(f"[SM:{self.ctx.goal_id}] REPLAN 진입 불가: {reason}")
            return False

        self.ctx.last_evaluation = evaluation
        self.ctx.iteration += 1
        return self._do_transition(
            GoalTrackerState.REPLAN,
            f"재계획 시작 (iter={self.ctx.iteration})",
            metadata={"done": evaluation.done_count, "total": evaluation.total_count},
        )

    def start_dispatch(self, task_ids: list[str]) -> bool:
        """REPLAN → DISPATCH 전이.

        Returns:
            True if 전이 성공 (태스크 있음), False if 태스크 없음.
        """
        if not self.can_enter_dispatch(len(task_ids)):
            logger.warning(
                f"[SM:{self.ctx.goal_id}] DISPATCH 진입 불가: 태스크 없음"
            )
            return False
        self.ctx.dispatched_task_ids = list(task_ids)
        return self._do_transition(
            GoalTrackerState.DISPATCH,
            f"dispatch 시작: {len(task_ids)}개 태스크",
            metadata={"task_ids": task_ids},
        )

    def return_to_idle(self, reason: str = "") -> bool:
        """현재 상태 → IDLE 전이 (dispatch 완료 / 목표 달성 / 정체 / 오류 공통).

        Returns:
            True if 전이 성공.
        """
        return self._do_transition(
            GoalTrackerState.IDLE,
            reason or "IDLE 복귀",
        )

    # ── 정체 관리 ─────────────────────────────────────────────────────────

    def record_stagnation(self) -> int:
        """정체 카운터 1 증가. 갱신된 stagnation_count 반환."""
        self.ctx.stagnation_count += 1
        self.ctx.updated_at = _utcnow()
        logger.info(
            f"[SM:{self.ctx.goal_id}] 정체 감지 "
            f"({self.ctx.stagnation_count}/{self.ctx.max_stagnation})"
        )
        return self.ctx.stagnation_count

    def reset_stagnation(self) -> None:
        """정체 카운터 초기화 (진전 감지 시)."""
        if self.ctx.stagnation_count > 0:
            logger.info(f"[SM:{self.ctx.goal_id}] 정체 카운터 리셋 (진전 감지)")
        self.ctx.stagnation_count = 0
        self.ctx.updated_at = _utcnow()

    # ── 종료 조건 ─────────────────────────────────────────────────────────

    def is_terminal(self) -> bool:
        """더 이상 진행 불가 상태 여부.

        조건 (OR):
            - iteration >= max_iterations
            - stagnation_count >= max_stagnation
        """
        if self.ctx.iteration >= self.ctx.max_iterations:
            return True
        if self.ctx.stagnation_count >= self.ctx.max_stagnation:
            return True
        return False

    def terminal_reason(self) -> str | None:
        """is_terminal()=True일 때 이유 반환."""
        if self.ctx.iteration >= self.ctx.max_iterations:
            return f"최대 반복 횟수 도달 ({self.ctx.max_iterations}회)"
        if self.ctx.stagnation_count >= self.ctx.max_stagnation:
            return f"정체 감지 ({self.ctx.stagnation_count}회 연속 진전 없음)"
        return None

    # ── 직렬화 ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """컨텍스트를 dict로 직렬화 (로깅·저장용)."""
        return {
            "goal_id": self.ctx.goal_id,
            "state": self.ctx.current_state.value,
            "iteration": self.ctx.iteration,
            "max_iterations": self.ctx.max_iterations,
            "stagnation_count": self.ctx.stagnation_count,
            "max_stagnation": self.ctx.max_stagnation,
            "is_terminal": self.is_terminal(),
            "terminal_reason": self.terminal_reason(),
            "dispatched_tasks": len(self.ctx.dispatched_task_ids),
            "history_length": len(self.ctx.history),
            "updated_at": self.ctx.updated_at.isoformat(),
        }

    # ── 범용 이벤트 인터페이스 ────────────────────────────────────────────────

    def get_state(self) -> GoalTrackerState:
        """현재 상태 반환 (state 프로퍼티 래퍼)."""
        return self.ctx.current_state

    def reset(self) -> None:
        """상태머신을 초기(IDLE) 상태로 완전 리셋.

        goal_id / max_iterations / max_stagnation 설정은 유지하고,
        iteration·stagnation·history·dispatched_task_ids 모두 초기화.
        """
        self.ctx = StateMachineContext(
            goal_id=self.ctx.goal_id,
            max_iterations=self.ctx.max_iterations,
            max_stagnation=self.ctx.max_stagnation,
        )
        logger.info(f"[SM:{self.ctx.goal_id}] 상태머신 리셋 → IDLE")

    def transition(self, event: "str | dict", **kwargs) -> bool:
        """이벤트 기반 범용 전이 메서드 — 전 조직 자율 루프 분기 로직.

        지원 이벤트 타입:
            ``"start_evaluate"``
                IDLE → EVALUATE 전이 시작.

            ``"evaluate_complete"``
                evaluate 결과에 따라 자율 분기:
                  - achieved=True  또는 stagnation 감지 → IDLE 복귀
                  - 미달성 + 정상  → REPLAN 전이
                payload 필수: ``evaluation=EvaluationResult``

            ``"replan_complete"``
                재계획 결과에 따라 자율 분기:
                  - task_ids 있음  → DISPATCH 전이
                  - task_ids 없음  → IDLE 복귀
                payload 선택: ``task_ids=list[str]``

            ``"dispatch_complete"``
                DISPATCH → IDLE 복귀.
                payload 선택: ``reason=str``

            ``"return_to_idle"``
                임의 상태 → IDLE 강제 복귀.
                payload 선택: ``reason=str``

        Args:
            event: 이벤트 타입 문자열 또는 ``{"type": ..., ...}`` dict.
            **kwargs: event가 str일 때 payload 인자로 사용.

        Returns:
            True if 전이 성공.

        Raises:
            InvalidTransitionError: 알 수 없는 이벤트 타입.
            ValueError: evaluate_complete 이벤트에 evaluation 누락.
        """
        # event 정규화
        if isinstance(event, dict):
            event_type: str = event.get("type", "")
            payload: dict = {k: v for k, v in event.items() if k != "type"}
        else:
            event_type = str(event)
            payload = kwargs

        # ── 분기 로직 ─────────────────────────────────────────────────────

        if event_type == "start_evaluate":
            return self.start_evaluate()

        elif event_type == "evaluate_complete":
            # 전 조직 자율 루프: evaluate 결과에 따라 replan vs idle 분기
            evaluation: Optional[EvaluationResult] = payload.get("evaluation")
            if evaluation is None:
                raise ValueError(
                    "evaluate_complete 이벤트에 'evaluation' (EvaluationResult) 필수"
                )

            # 정체 감지 업데이트
            last_eval = self.ctx.last_evaluation
            if (
                last_eval is not None
                and evaluation.done_count == last_eval.done_count
                and not evaluation.achieved
            ):
                self.record_stagnation()
            elif not evaluation.achieved and evaluation.done_count > 0:
                self.reset_stagnation()

            if self.can_enter_replan(evaluation):
                # 미달성 + 정상 진행 → REPLAN
                return self.start_replan(evaluation)
            else:
                # 달성 or 정체 → IDLE 복귀
                if evaluation.achieved:
                    reason = f"목표 달성 (confidence={evaluation.confidence:.2f})"
                elif self.ctx.stagnation_count >= self.ctx.max_stagnation:
                    reason = (
                        f"정체 감지 {self.ctx.stagnation_count}/{self.ctx.max_stagnation}회"
                    )
                else:
                    reason = "최대 반복 도달"
                return self.return_to_idle(reason)

        elif event_type == "replan_complete":
            # 재계획 완료: task_ids 있으면 DISPATCH, 없으면 IDLE
            task_ids: list[str] = payload.get("task_ids", [])
            if self.can_enter_dispatch(len(task_ids)):
                return self.start_dispatch(task_ids)
            else:
                return self.return_to_idle("재계획 태스크 없음")

        elif event_type == "dispatch_complete":
            reason: str = payload.get("reason", "dispatch 완료")
            return self.return_to_idle(reason)

        elif event_type == "return_to_idle":
            reason = payload.get("reason", "")
            return self.return_to_idle(reason)

        else:
            raise InvalidTransitionError(f"알 수 없는 이벤트 타입: '{event_type}'")

    def __repr__(self) -> str:
        return (
            f"<GoalTrackerStateMachine goal={self.ctx.goal_id} "
            f"state={self.ctx.current_state.value} "
            f"iter={self.ctx.iteration}/{self.ctx.max_iterations}>"
        )
