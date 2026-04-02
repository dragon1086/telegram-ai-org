"""OKR 주기적 활동 테스트 (Phase 3)."""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.context_db import ContextDB
from core.goal_tracker import GoalTracker, GoalType
from core.okr_periodic_activities import OKRPeriodicActivities


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
def periodic(db, tracker):
    return OKRPeriodicActivities(
        context_db=db, goal_tracker=tracker,
    )


async def _setup_full_hierarchy(tracker):
    """테스트용 OKR 계층 생성."""
    obj_id = await tracker.create_objective(
        title="MAU 10만", description="연간 목표",
        deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="Q2 가입 3만", description="분기 KR",
        parent_objective_id=obj_id, deadline="2026-06-30",
        kpi_metric="signups", kpi_target=30000,
        weight=1.0,
    )
    init_id = await tracker.create_initiative(
        title="SNS 캠페인", description="소셜 마케팅",
        parent_kr_id=kr_id, deadline="2026-05-31",
    )
    t1 = await tracker.start_goal(
        title="인스타 광고", description="광고 집행",
        goal_type=GoalType.TASK, parent_goal_id=init_id,
    )
    t2 = await tracker.start_goal(
        title="틱톡 광고", description="틱톡 집행",
        goal_type=GoalType.TASK, parent_goal_id=init_id,
    )
    return obj_id, kr_id, init_id, t1, t2


class TestDailyRetro:
    """일일 회고 테스트."""

    @pytest.mark.asyncio
    async def test_records_task_snapshots(self, db, tracker, periodic):
        await db.initialize()
        _, _, _, t1, t2 = await _setup_full_hierarchy(tracker)
        await db.update_goal(t1, progress=0.5)
        await db.update_goal(t2, progress=0.3)

        report = await periodic.run_daily_retro(date="2026-04-02")

        assert report.activity_type == "daily_retro"
        assert report.goals_checked == 2
        assert report.snapshots_recorded == 2
        assert "Task 2개" in report.summary

        # 스냅샷 확인
        s1 = await db.get_progress_snapshots(t1, snapshot_type="daily")
        assert len(s1) == 1
        assert s1[0]["snapshot_date"] == "2026-04-02"

    @pytest.mark.asyncio
    async def test_empty_tasks(self, db, tracker, periodic):
        await db.initialize()
        report = await periodic.run_daily_retro(date="2026-04-02")
        assert report.goals_checked == 0
        assert report.snapshots_recorded == 0


class TestWeeklyReview:
    """주간 점검 테스트."""

    @pytest.mark.asyncio
    async def test_updates_initiative_progress(self, db, tracker, periodic):
        await db.initialize()
        obj_id, kr_id, init_id, t1, t2 = await _setup_full_hierarchy(tracker)
        await db.update_goal(t1, progress=0.8)
        await db.update_goal(t2, progress=0.6)

        report = await periodic.run_weekly_review(date="2026-04-02")

        assert report.activity_type == "weekly_review"
        assert report.goals_checked >= 1  # initiative + kr

        # Initiative progress 재계산됨
        init = await db.get_goal(init_id)
        assert abs(init["progress"] - 0.7) < 0.01  # (0.8 + 0.6) / 2

    @pytest.mark.asyncio
    async def test_kr_hierarchy_updated(self, db, tracker, periodic):
        await db.initialize()
        obj_id, kr_id, init_id, t1, t2 = await _setup_full_hierarchy(tracker)
        await tracker.update_kpi(kr_id, kpi_current=15000)

        await periodic.run_weekly_review(date="2026-04-02")

        kr = await db.get_goal(kr_id)
        assert abs(kr["progress"] - 0.5) < 0.01


class TestMonthlyReview:
    """월간 리뷰 테스트."""

    @pytest.mark.asyncio
    async def test_records_kr_snapshots(self, db, tracker, periodic):
        await db.initialize()
        obj_id, kr_id, _, _, _ = await _setup_full_hierarchy(tracker)
        await tracker.update_kpi(kr_id, kpi_current=20000)

        report = await periodic.run_monthly_review(date="2026-04-30")

        assert report.activity_type == "monthly_review"
        assert report.snapshots_recorded >= 1

        snapshots = await db.get_progress_snapshots(kr_id, snapshot_type="monthly")
        assert len(snapshots) == 1
        assert snapshots[0]["snapshot_date"] == "2026-04-30"

    @pytest.mark.asyncio
    async def test_objective_updated(self, db, tracker, periodic):
        await db.initialize()
        obj_id, kr_id, _, _, _ = await _setup_full_hierarchy(tracker)
        await tracker.update_kpi(kr_id, kpi_current=24000)

        await periodic.run_monthly_review(date="2026-04-30")

        obj = await db.get_goal(obj_id)
        assert abs(obj["progress"] - 0.8) < 0.01


class TestQuarterlyEval:
    """분기 평가 테스트."""

    @pytest.mark.asyncio
    async def test_grades_objectives(self, db, tracker, periodic):
        await db.initialize()
        obj_id, kr_id, _, _, _ = await _setup_full_hierarchy(tracker)
        await tracker.update_kpi(kr_id, kpi_current=27000)  # 90%

        report = await periodic.run_quarterly_eval(date="2026-06-30")

        assert report.activity_type == "quarterly_eval"
        assert report.goals_checked == 1
        assert report.details[0]["grade"] == "S"
        assert report.details[0]["rollover_candidate"] is False

    @pytest.mark.asyncio
    async def test_identifies_rollover_candidates(self, db, tracker, periodic):
        await db.initialize()
        obj_id, kr_id, _, _, _ = await _setup_full_hierarchy(tracker)
        await tracker.update_kpi(kr_id, kpi_current=9000)  # 30%

        report = await periodic.run_quarterly_eval(date="2026-06-30")

        assert report.details[0]["grade"] == "D"
        assert report.details[0]["rollover_candidate"] is True
        assert report.alerts_generated == 1

    @pytest.mark.asyncio
    async def test_grade_scale(self, db, periodic):
        """등급 스케일 확인."""
        assert periodic._grade(0.95) == "S"
        assert periodic._grade(0.85) == "A"
        assert periodic._grade(0.75) == "B"
        assert periodic._grade(0.55) == "C"
        assert periodic._grade(0.35) == "D"
        assert periodic._grade(0.1) == "F"
