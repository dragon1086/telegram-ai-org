"""DeadlineChecker 시간 기반 알림 테스트 (Phase 1.4)."""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.context_db import ContextDB
from core.goal_tracker import (
    DeadlineChecker,
    DeadlineSeverity,
    GoalTracker,
)


@pytest.fixture
def db(tmp_path):
    return ContextDB(str(tmp_path / "test.db"))


@pytest.fixture
def checker(db):
    return DeadlineChecker(db)


@pytest.fixture
def tracker(db):
    orch = AsyncMock()
    send = AsyncMock()
    return GoalTracker(
        context_db=db, orchestrator=orch,
        telegram_send_func=send, org_id="pm",
    )


class TestDeadlineSeverityClassification:
    """심각도 분류 테스트."""

    def test_no_deadline(self, checker):
        """deadline 미설정 → None."""
        goal = {"id": "G-1", "title": "Test"}
        assert checker.check_deadline(goal) is None

    def test_emergency_past_deadline(self, checker):
        """마감 초과 → EMERGENCY."""
        now = datetime(2026, 4, 10, tzinfo=timezone.utc)
        goal = {"id": "G-1", "title": "Past", "deadline": "2026-04-05",
                "goal_type": "task", "progress": 0.3}
        alert = checker.check_deadline(goal, now=now)
        assert alert is not None
        assert alert.severity == DeadlineSeverity.EMERGENCY
        assert alert.days_remaining < 0
        assert "초과" in alert.message

    def test_critical_1_day(self, checker):
        """마감 1일 남음 → CRITICAL."""
        now = datetime(2026, 4, 9, tzinfo=timezone.utc)
        goal = {"id": "G-1", "title": "Urgent", "deadline": "2026-04-10",
                "goal_type": "key_result", "progress": 0.5}
        alert = checker.check_deadline(goal, now=now)
        assert alert.severity == DeadlineSeverity.CRITICAL
        assert alert.days_remaining == 1

    def test_critical_3_days(self, checker):
        """마감 3일 남음 → CRITICAL."""
        now = datetime(2026, 4, 7, tzinfo=timezone.utc)
        goal = {"id": "G-1", "title": "Soon", "deadline": "2026-04-10",
                "goal_type": "initiative", "progress": 0.8}
        alert = checker.check_deadline(goal, now=now)
        assert alert.severity == DeadlineSeverity.CRITICAL

    def test_warning_5_days(self, checker):
        """마감 5일 남음 → WARNING."""
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        goal = {"id": "G-1", "title": "Approaching", "deadline": "2026-04-10",
                "goal_type": "task", "progress": 0.6}
        alert = checker.check_deadline(goal, now=now)
        assert alert.severity == DeadlineSeverity.WARNING
        assert "점검 권장" in alert.message

    def test_info_10_days(self, checker):
        """마감 10일 남음 → INFO."""
        now = datetime(2026, 3, 31, tzinfo=timezone.utc)
        goal = {"id": "G-1", "title": "Later", "deadline": "2026-04-10",
                "goal_type": "objective", "progress": 0.2}
        alert = checker.check_deadline(goal, now=now)
        assert alert.severity == DeadlineSeverity.INFO

    def test_none_15_days(self, checker):
        """마감 15일 남음 → None (NONE 심각도)."""
        now = datetime(2026, 3, 26, tzinfo=timezone.utc)
        goal = {"id": "G-1", "title": "Far", "deadline": "2026-04-10",
                "goal_type": "task", "progress": 0.1}
        alert = checker.check_deadline(goal, now=now)
        assert alert is None

    def test_invalid_deadline_format(self, checker):
        """잘못된 날짜 형식 → None."""
        goal = {"id": "G-1", "title": "Bad", "deadline": "not-a-date"}
        assert checker.check_deadline(goal) is None


class TestDeadlineCheckerAsync:
    """비동기 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_check_all_active(self, db, checker, tracker):
        """활성 목표 전체 마감 확인."""
        await db.initialize()
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)

        # 마감 임박 목표
        await tracker.create_objective(
            title="Urgent Obj", description="urgent",
            deadline="2026-04-06",
        )
        # 여유 있는 목표
        await tracker.create_objective(
            title="Safe Obj", description="safe",
            deadline="2026-06-30",
        )
        # 마감 초과 목표
        await tracker.create_objective(
            title="Overdue Obj", description="overdue",
            deadline="2026-04-01",
        )

        alerts = await checker.check_all_active(now=now)
        assert len(alerts) == 2  # Safe는 NONE이므로 제외
        # 심각도순 정렬: emergency → critical
        assert alerts[0].severity == DeadlineSeverity.EMERGENCY
        assert alerts[1].severity == DeadlineSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_check_by_type(self, db, checker, tracker):
        """goal_type별 마감 확인."""
        await db.initialize()
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)

        await tracker.create_objective(
            title="Obj1", description="o1", deadline="2026-04-08",
        )
        await tracker.create_key_result(
            title="KR1", description="kr1",
            parent_objective_id="G-pm-001", deadline="2026-04-07",
        )

        obj_alerts = await checker.check_by_type("objective", now=now)
        assert len(obj_alerts) == 1
        assert obj_alerts[0].goal_type == "objective"

        kr_alerts = await checker.check_by_type("key_result", now=now)
        assert len(kr_alerts) == 1
        assert kr_alerts[0].goal_type == "key_result"

    @pytest.mark.asyncio
    async def test_progress_in_alert(self, db, checker, tracker):
        """알림에 진척률 포함."""
        await db.initialize()
        now = datetime(2026, 4, 8, tzinfo=timezone.utc)

        kr_id = await tracker.create_key_result(
            title="KR Progress", description="kr",
            parent_objective_id="O-none", deadline="2026-04-10",
            kpi_metric="users", kpi_target=1000,
        )
        await tracker.update_kpi(kr_id, kpi_current=750)

        alerts = await checker.check_all_active(now=now)
        assert len(alerts) >= 1
        kr_alert = [a for a in alerts if a.goal_id == kr_id][0]
        assert abs(kr_alert.progress - 0.75) < 0.01
        assert "75%" in kr_alert.message

    @pytest.mark.asyncio
    async def test_same_day_deadline(self, db, checker, tracker):
        """마감일 당일 → CRITICAL (0일 남음)."""
        await db.initialize()
        now = datetime(2026, 4, 10, tzinfo=timezone.utc)

        await tracker.create_objective(
            title="Today", description="today",
            deadline="2026-04-10",
        )
        alerts = await checker.check_all_active(now=now)
        assert len(alerts) == 1
        assert alerts[0].severity == DeadlineSeverity.CRITICAL
        assert alerts[0].days_remaining == 0
