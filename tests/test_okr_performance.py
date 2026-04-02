"""OKR 성과평가 + 성격진화 테스트 (Phase 4)."""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.context_db import ContextDB
from core.goal_tracker import GoalTracker, GoalType
from core.okr_performance_evaluator import PerformanceEvaluator


@pytest.fixture
def db(tmp_path):
    return ContextDB(str(tmp_path / "test.db"))


@pytest.fixture
def tracker(db):
    orch = AsyncMock()
    send = AsyncMock()
    return GoalTracker(
        context_db=db, orchestrator=orch,
        telegram_send_func=send, org_id="pm",
    )


@pytest.fixture
def evaluator(db, tracker):
    return PerformanceEvaluator(
        context_db=db, goal_tracker=tracker,
    )


async def _setup_dept_tasks(db, tracker):
    """개발실 Task + OKR 계층 생성."""
    obj_id = await tracker.create_objective(
        title="제품 안정화", description="연간",
        deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="버그 제로", description="kr",
        parent_objective_id=obj_id, deadline="2026-06-30",
        kpi_metric="bugs", kpi_target=0,
    )
    init_id = await tracker.create_initiative(
        title="코드 리뷰 강화", description="init",
        parent_kr_id=kr_id,
    )
    # 개발실 Task들
    t1_id = await tracker.start_goal(
        title="버그 A 수정", description="bug fix",
        goal_type=GoalType.TASK, parent_goal_id=init_id,
        org_id="engineering",
    )
    await db.update_goal(t1_id, status="achieved", created_by="engineering")

    t2_id = await tracker.start_goal(
        title="버그 B 수정", description="bug fix 2",
        goal_type=GoalType.TASK, parent_goal_id=init_id,
        org_id="engineering",
    )
    await db.update_goal(t2_id, status="achieved", created_by="engineering")

    t3_id = await tracker.start_goal(
        title="리팩토링", description="refactor",
        goal_type=GoalType.TASK, parent_goal_id=init_id,
        org_id="engineering",
    )
    await db.update_goal(t3_id, created_by="engineering")
    # t3는 아직 active

    return obj_id, kr_id, init_id, [t1_id, t2_id, t3_id]


class TestPerformanceEvaluator:
    """성과 평가 테스트."""

    @pytest.mark.asyncio
    async def test_evaluate_department(self, db, tracker, evaluator):
        """부서 평가 실행."""
        await db.initialize()
        await _setup_dept_tasks(db, tracker)

        result = await evaluator.evaluate_department(
            dept_id="engineering",
            period_start="2026-01-01",
            period_end="2026-03-31",
        )

        assert result.dept_id == "engineering"
        assert result.period_type == "quarterly"
        assert 0 <= result.overall_score <= 100
        assert result.grade in ("S", "A", "B", "C", "D", "F")
        assert "completion_rate" in result.criteria_scores

    @pytest.mark.asyncio
    async def test_completion_rate(self, db, tracker, evaluator):
        """완료율 계산 확인."""
        await db.initialize()
        await _setup_dept_tasks(db, tracker)

        result = await evaluator.evaluate_department(
            dept_id="engineering",
            period_start="2026-01-01",
            period_end="2026-03-31",
        )

        # 3개 중 2개 완료 → 66.7%
        cr = result.criteria_scores["completion_rate"]
        assert abs(cr - 66.7) < 1.0

    @pytest.mark.asyncio
    async def test_prompt_fragment_generation(self, db, tracker, evaluator):
        """프롬프트 프래그먼트 생성."""
        await db.initialize()
        await _setup_dept_tasks(db, tracker)

        result = await evaluator.evaluate_department(
            dept_id="engineering",
            period_start="2026-01-01",
            period_end="2026-03-31",
        )

        assert "[성과 평가 결과:" in result.prompt_fragment
        assert result.grade in result.prompt_fragment

    @pytest.mark.asyncio
    async def test_evaluation_saved_to_db(self, db, tracker, evaluator):
        """평가 결과 DB 저장 확인."""
        await db.initialize()
        await _setup_dept_tasks(db, tracker)

        await evaluator.evaluate_department(
            dept_id="engineering",
            period_start="2026-01-01",
            period_end="2026-03-31",
        )

        evals = await db.get_performance_evaluations(dept_id="engineering")
        assert len(evals) == 1
        assert evals[0]["grade"] in ("S", "A", "B", "C", "D", "F")
        assert "completion_rate" in evals[0]["criteria_scores"]

    @pytest.mark.asyncio
    async def test_empty_department(self, db, tracker, evaluator):
        """태스크 없는 부서 평가."""
        await db.initialize()

        result = await evaluator.evaluate_department(
            dept_id="design",
            period_start="2026-01-01",
            period_end="2026-03-31",
        )

        assert result.criteria_scores["completion_rate"] == 0.0
        assert result.grade in ("C", "D", "F")

    @pytest.mark.asyncio
    async def test_strengths_weaknesses(self, db, tracker, evaluator):
        """강점/약점 식별."""
        await db.initialize()
        await _setup_dept_tasks(db, tracker)

        result = await evaluator.evaluate_department(
            dept_id="engineering",
            period_start="2026-01-01",
            period_end="2026-03-31",
        )

        # 강점: 80점 이상, 약점: 50점 미만
        assert isinstance(result.strengths, list)
        assert isinstance(result.weaknesses, list)


class TestGrading:
    """등급 산정 테스트."""

    def test_grade_scale(self, evaluator):
        assert evaluator._grade(95) == "S"
        assert evaluator._grade(85) == "A"
        assert evaluator._grade(75) == "B"
        assert evaluator._grade(55) == "C"
        assert evaluator._grade(35) == "D"
        assert evaluator._grade(15) == "F"

    def test_weighted_score(self, evaluator):
        criteria = {
            "completion_rate": 80,
            "quality": 70,
            "speed": 90,
            "kr_contribution": 60,
            "collaboration": 50,
        }
        score = evaluator._weighted_score(criteria)
        expected = (80*0.3 + 70*0.25 + 90*0.2 + 60*0.15 + 50*0.1)
        assert abs(score - expected) < 0.1
