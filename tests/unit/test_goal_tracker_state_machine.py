"""GoalTrackerStateMachine 단위 테스트.

검증 범위:
    1. idle→evaluate→replan→dispatch 전체 전이 시나리오
    2. evaluate 결과에 따른 replan vs dispatch 분기
    3. 잘못된 이벤트 예외 처리
    4. get_state() / reset() / transition() 신규 메서드
    5. 정체 감지 + 터미널 상태
    6. to_dict() 직렬화
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from goal_tracker.state_machine import (
    EvaluationResult,
    GoalTrackerState,
    GoalTrackerStateMachine,
    InvalidTransitionError,
    StateMachineContext,
    StateTransition,
)


# ── 픽스처 ────────────────────────────────────────────────────────────────────

@pytest.fixture
def sm() -> GoalTrackerStateMachine:
    return GoalTrackerStateMachine("G-test-001", max_iterations=5, max_stagnation=3)


@pytest.fixture
def eval_not_achieved() -> EvaluationResult:
    return EvaluationResult(
        achieved=False, progress_pct=0.4, done_count=2, total_count=5
    )


@pytest.fixture
def eval_achieved() -> EvaluationResult:
    return EvaluationResult(
        achieved=True, progress_pct=1.0, done_count=5, total_count=5, confidence=0.95
    )


# ════════════════════════════════════════════════════════════════════════════
# 1. 초기 상태 검증
# ════════════════════════════════════════════════════════════════════════════

class TestInitialState:
    def test_initial_state_is_idle(self, sm):
        assert sm.state == GoalTrackerState.IDLE

    def test_get_state_returns_idle(self, sm):
        assert sm.get_state() == GoalTrackerState.IDLE

    def test_goal_id_preserved(self, sm):
        assert sm.goal_id == "G-test-001"

    def test_iteration_starts_at_zero(self, sm):
        assert sm.ctx.iteration == 0

    def test_stagnation_starts_at_zero(self, sm):
        assert sm.ctx.stagnation_count == 0


# ════════════════════════════════════════════════════════════════════════════
# 2. 전체 전이 시나리오 (idle→evaluate→replan→dispatch→idle)
# ════════════════════════════════════════════════════════════════════════════

class TestFullTransitionScenario:
    def test_idle_to_evaluate(self, sm):
        assert sm.start_evaluate()
        assert sm.state == GoalTrackerState.EVALUATE

    def test_evaluate_to_replan(self, sm, eval_not_achieved):
        sm.start_evaluate()
        assert sm.start_replan(eval_not_achieved)
        assert sm.state == GoalTrackerState.REPLAN

    def test_replan_to_dispatch(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        task_ids = ["T-001", "T-002", "T-003"]
        assert sm.start_dispatch(task_ids)
        assert sm.state == GoalTrackerState.DISPATCH

    def test_dispatch_to_idle(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        sm.start_dispatch(["T-001"])
        assert sm.return_to_idle("dispatch 완료")
        assert sm.state == GoalTrackerState.IDLE

    def test_full_loop_increments_iteration(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        assert sm.ctx.iteration == 1
        sm.start_dispatch(["T-001"])
        sm.return_to_idle()
        # 두 번째 루프
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        assert sm.ctx.iteration == 2

    def test_history_records_all_transitions(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        sm.start_dispatch(["T-001"])
        sm.return_to_idle()
        assert len(sm.ctx.history) == 4

    def test_transition_history_contains_correct_states(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        sm.start_dispatch(["T-001"])
        sm.return_to_idle()
        states = [(t.from_state, t.to_state) for t in sm.ctx.history]
        assert states == [
            (GoalTrackerState.IDLE, GoalTrackerState.EVALUATE),
            (GoalTrackerState.EVALUATE, GoalTrackerState.REPLAN),
            (GoalTrackerState.REPLAN, GoalTrackerState.DISPATCH),
            (GoalTrackerState.DISPATCH, GoalTrackerState.IDLE),
        ]


# ════════════════════════════════════════════════════════════════════════════
# 3. 분기 조건: replan vs dispatch
# ════════════════════════════════════════════════════════════════════════════

class TestBranchConditions:
    def test_achieved_blocks_replan(self, sm, eval_achieved):
        sm.start_evaluate()
        assert not sm.start_replan(eval_achieved)
        assert sm.state == GoalTrackerState.EVALUATE  # 전이 안 됨

    def test_achieved_returns_to_idle(self, sm, eval_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_achieved)  # False 반환
        sm.return_to_idle("목표 달성")
        assert sm.state == GoalTrackerState.IDLE

    def test_empty_task_ids_blocks_dispatch(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        assert not sm.start_dispatch([])
        assert sm.state == GoalTrackerState.REPLAN  # 전이 안 됨

    def test_stagnation_blocks_replan(self, sm, eval_not_achieved):
        # 정체 카운터를 max에 도달시킴
        sm.ctx.stagnation_count = sm.ctx.max_stagnation
        sm.start_evaluate()
        assert not sm.start_replan(eval_not_achieved)

    def test_max_iterations_blocks_evaluate(self, sm):
        sm.ctx.iteration = sm.ctx.max_iterations
        assert not sm.start_evaluate()
        assert sm.state == GoalTrackerState.IDLE


# ════════════════════════════════════════════════════════════════════════════
# 4. transition() 이벤트 기반 범용 인터페이스
# ════════════════════════════════════════════════════════════════════════════

class TestTransitionMethod:
    def test_start_evaluate_event(self, sm):
        result = sm.transition("start_evaluate")
        assert result is True
        assert sm.state == GoalTrackerState.EVALUATE

    def test_evaluate_complete_replan_branch(self, sm, eval_not_achieved):
        sm.start_evaluate()
        result = sm.transition("evaluate_complete", evaluation=eval_not_achieved)
        assert result is True
        assert sm.state == GoalTrackerState.REPLAN

    def test_evaluate_complete_idle_branch_when_achieved(self, sm, eval_achieved):
        sm.start_evaluate()
        result = sm.transition("evaluate_complete", evaluation=eval_achieved)
        # achieved → can_enter_replan() = False → return_to_idle()
        assert result is True
        assert sm.state == GoalTrackerState.IDLE

    def test_replan_complete_dispatch_branch(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        result = sm.transition("replan_complete", task_ids=["T-001", "T-002"])
        assert result is True
        assert sm.state == GoalTrackerState.DISPATCH

    def test_replan_complete_idle_branch_no_tasks(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        result = sm.transition("replan_complete", task_ids=[])
        assert result is True
        assert sm.state == GoalTrackerState.IDLE

    def test_dispatch_complete_event(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        sm.start_dispatch(["T-001"])
        result = sm.transition("dispatch_complete", reason="완료")
        assert result is True
        assert sm.state == GoalTrackerState.IDLE

    def test_return_to_idle_event(self, sm):
        sm.start_evaluate()
        result = sm.transition("return_to_idle", reason="수동 복귀")
        assert result is True
        assert sm.state == GoalTrackerState.IDLE

    def test_dict_event_format(self, sm):
        result = sm.transition({"type": "start_evaluate"})
        assert result is True
        assert sm.state == GoalTrackerState.EVALUATE

    def test_evaluate_complete_missing_evaluation_raises(self, sm):
        sm.start_evaluate()
        with pytest.raises(ValueError, match="evaluation"):
            sm.transition("evaluate_complete")

    def test_unknown_event_raises(self, sm):
        with pytest.raises(InvalidTransitionError, match="알 수 없는"):
            sm.transition("unknown_event_xyz")


# ════════════════════════════════════════════════════════════════════════════
# 5. get_state() / reset()
# ════════════════════════════════════════════════════════════════════════════

class TestGetStateAndReset:
    def test_get_state_reflects_current_state(self, sm, eval_not_achieved):
        assert sm.get_state() == GoalTrackerState.IDLE
        sm.start_evaluate()
        assert sm.get_state() == GoalTrackerState.EVALUATE
        sm.start_replan(eval_not_achieved)
        assert sm.get_state() == GoalTrackerState.REPLAN

    def test_reset_returns_to_idle(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        sm.reset()
        assert sm.state == GoalTrackerState.IDLE

    def test_reset_clears_iteration(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        sm.reset()
        assert sm.ctx.iteration == 0

    def test_reset_clears_history(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        sm.reset()
        assert len(sm.ctx.history) == 0

    def test_reset_clears_stagnation(self, sm):
        sm.record_stagnation()
        sm.record_stagnation()
        sm.reset()
        assert sm.ctx.stagnation_count == 0

    def test_reset_preserves_goal_id(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.reset()
        assert sm.goal_id == "G-test-001"

    def test_reset_preserves_max_iterations(self, sm):
        sm.reset()
        assert sm.ctx.max_iterations == 5

    def test_reset_preserves_max_stagnation(self, sm):
        sm.reset()
        assert sm.ctx.max_stagnation == 3


# ════════════════════════════════════════════════════════════════════════════
# 6. 정체 감지 + 터미널 상태
# ════════════════════════════════════════════════════════════════════════════

class TestStagnationAndTerminal:
    def test_record_stagnation_increments(self, sm):
        count = sm.record_stagnation()
        assert count == 1
        count = sm.record_stagnation()
        assert count == 2

    def test_reset_stagnation_clears(self, sm):
        sm.record_stagnation()
        sm.record_stagnation()
        sm.reset_stagnation()
        assert sm.ctx.stagnation_count == 0

    def test_is_terminal_at_max_iterations(self, sm):
        sm.ctx.iteration = 5
        assert sm.is_terminal()

    def test_is_terminal_at_max_stagnation(self, sm):
        sm.ctx.stagnation_count = 3
        assert sm.is_terminal()

    def test_not_terminal_when_normal(self, sm):
        sm.ctx.iteration = 2
        sm.ctx.stagnation_count = 1
        assert not sm.is_terminal()

    def test_terminal_reason_max_iterations(self, sm):
        sm.ctx.iteration = 5
        reason = sm.terminal_reason()
        assert reason is not None
        assert "반복" in reason

    def test_terminal_reason_stagnation(self, sm):
        sm.ctx.stagnation_count = 3
        reason = sm.terminal_reason()
        assert reason is not None
        assert "정체" in reason

    def test_terminal_reason_none_when_not_terminal(self, sm):
        assert sm.terminal_reason() is None

    def test_stagnation_via_transition_evaluate_complete(self, sm):
        """transition evaluate_complete: 동일 done_count 반복 시 stagnation 증가."""
        first_eval = EvaluationResult(
            achieved=False, progress_pct=0.3, done_count=2, total_count=5
        )
        # 첫 번째 evaluate
        sm.start_evaluate()
        sm.transition("evaluate_complete", evaluation=first_eval)
        # 두 번째 evaluate: 동일 done_count
        sm.start_evaluate()
        second_eval = EvaluationResult(
            achieved=False, progress_pct=0.3, done_count=2, total_count=5
        )
        sm.transition("evaluate_complete", evaluation=second_eval)
        # stagnation이 증가했어야 함
        assert sm.ctx.stagnation_count >= 1


# ════════════════════════════════════════════════════════════════════════════
# 7. can_transition / 허용되지 않는 전이
# ════════════════════════════════════════════════════════════════════════════

class TestInvalidTransitions:
    def test_cannot_transition_idle_to_dispatch(self, sm):
        assert not sm.can_transition(GoalTrackerState.DISPATCH)

    def test_cannot_transition_idle_to_replan(self, sm):
        assert not sm.can_transition(GoalTrackerState.REPLAN)

    def test_dispatch_cannot_go_to_evaluate(self, sm, eval_not_achieved):
        sm.start_evaluate()
        sm.start_replan(eval_not_achieved)
        sm.start_dispatch(["T-001"])
        assert not sm.can_transition(GoalTrackerState.EVALUATE)

    def test_do_transition_returns_false_on_invalid(self, sm):
        result = sm._do_transition(GoalTrackerState.DISPATCH, "test")
        assert result is False
        assert sm.state == GoalTrackerState.IDLE  # 변경되지 않음


# ════════════════════════════════════════════════════════════════════════════
# 8. to_dict() 직렬화
# ════════════════════════════════════════════════════════════════════════════

class TestSerialization:
    def test_to_dict_keys(self, sm):
        d = sm.to_dict()
        required_keys = {
            "goal_id", "state", "iteration", "max_iterations",
            "stagnation_count", "max_stagnation",
            "is_terminal", "terminal_reason",
            "dispatched_tasks", "history_length", "updated_at",
        }
        assert required_keys.issubset(d.keys())

    def test_to_dict_goal_id(self, sm):
        assert sm.to_dict()["goal_id"] == "G-test-001"

    def test_to_dict_state_value(self, sm):
        assert sm.to_dict()["state"] == "idle"

    def test_repr_contains_goal_id(self, sm):
        assert "G-test-001" in repr(sm)

    def test_repr_contains_state(self, sm):
        assert "idle" in repr(sm)
