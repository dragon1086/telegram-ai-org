"""OKR 대시보드 테스트 (Phase 5)."""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.context_db import ContextDB
from core.goal_tracker import GoalTracker, GoalType
from core.okr_dashboard import OKRDashboard


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
def dashboard(db, tracker):
    return OKRDashboard(
        context_db=db, goal_tracker=tracker,
    )


async def _setup_full_hierarchy(db, tracker):
    """테스트용 OKR 계층 생성."""
    obj_id = await tracker.create_objective(
        title="MAU 10만 달성", description="연간 목표",
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
        parent_kr_id=kr_id,
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


class TestDashboardGeneration:
    """대시보드 생성 테스트."""

    @pytest.mark.asyncio
    async def test_empty_dashboard(self, db, dashboard):
        """Objective 없을 때."""
        await db.initialize()
        result = await dashboard.generate_full_dashboard(date="2026-04-02")
        assert "📊 OKR 대시보드 (2026-04-02)" in result
        assert "등록된 Objective가 없습니다" in result

    @pytest.mark.asyncio
    async def test_full_dashboard_structure(self, db, tracker, dashboard):
        """전체 대시보드 구조 확인."""
        await db.initialize()
        await _setup_full_hierarchy(db, tracker)

        result = await dashboard.generate_full_dashboard(date="2026-04-02")

        assert "📊 OKR 대시보드 (2026-04-02)" in result
        assert "━━━━" in result
        assert "🎯 MAU 10만 달성" in result
        assert "📈 Q2 가입 3만" in result
        assert "📋 SNS 캠페인" in result
        assert "전체 진척률" in result

    @pytest.mark.asyncio
    async def test_dashboard_with_progress(self, db, tracker, dashboard):
        """진행률 반영 확인."""
        await db.initialize()
        obj_id, kr_id, init_id, t1, t2 = await _setup_full_hierarchy(
            db, tracker,
        )
        await db.update_goal(t1, progress=1.0, status="achieved")
        await db.update_goal(t2, progress=0.4)

        result = await dashboard.generate_full_dashboard(date="2026-04-02")

        # 인스타 완료(100%) + 틱톡 40% → 대시보드에 반영
        assert "▓" in result
        assert "░" in result

    @pytest.mark.asyncio
    async def test_dashboard_with_kpi(self, db, tracker, dashboard):
        """KPI 현황 표시 확인."""
        await db.initialize()
        obj_id, kr_id, _, _, _ = await _setup_full_hierarchy(db, tracker)
        await tracker.update_kpi(kr_id, kpi_current=15000)

        result = await dashboard.generate_full_dashboard(date="2026-04-02")

        assert "(15000/30000" in result

    @pytest.mark.asyncio
    async def test_dashboard_deadline_display(self, db, tracker, dashboard):
        """마감일 D-day 표시."""
        await db.initialize()
        await _setup_full_hierarchy(db, tracker)

        result = await dashboard.generate_full_dashboard(date="2026-04-02")

        # deadline="2026-12-31", date="2026-04-02" → D-273
        assert "D-" in result


class TestObjectiveDetail:
    """Objective 상세 대시보드 테스트."""

    @pytest.mark.asyncio
    async def test_detail_not_found(self, db, dashboard):
        """존재하지 않는 Objective."""
        await db.initialize()
        result = await dashboard.generate_objective_detail("nonexistent")
        assert "❌" in result

    @pytest.mark.asyncio
    async def test_detail_rendering(self, db, tracker, dashboard):
        """상세 대시보드 렌더링."""
        await db.initialize()
        obj_id, _, _, _, _ = await _setup_full_hierarchy(db, tracker)

        result = await dashboard.generate_objective_detail(
            obj_id, date="2026-04-02",
        )

        assert "🎯 MAU 10만 달성" in result
        assert "📈 Q2 가입 3만" in result


class TestProgressBar:
    """진행 바 테스트."""

    def test_zero_progress(self, dashboard):
        bar = dashboard._progress_bar(0.0)
        assert bar == "[░░░░░░░░░░]"

    def test_full_progress(self, dashboard):
        bar = dashboard._progress_bar(1.0)
        assert bar == "[▓▓▓▓▓▓▓▓▓▓]"

    def test_half_progress(self, dashboard):
        bar = dashboard._progress_bar(0.5)
        assert bar == "[▓▓▓▓▓░░░░░]"

    def test_over_100_clamped(self, dashboard):
        bar = dashboard._progress_bar(1.5)
        assert bar == "[▓▓▓▓▓▓▓▓▓▓]"

    def test_negative_clamped(self, dashboard):
        bar = dashboard._progress_bar(-0.3)
        assert bar == "[░░░░░░░░░░]"


class TestDeadlineFormat:
    """마감일 포맷 테스트."""

    def test_no_deadline(self, dashboard):
        result = dashboard._format_deadline({}, "2026-04-02")
        assert result == ""

    def test_future_deadline(self, dashboard):
        result = dashboard._format_deadline(
            {"deadline": "2026-12-31"}, "2026-04-02",
        )
        assert "⏰ D-" in result

    def test_overdue_deadline(self, dashboard):
        result = dashboard._format_deadline(
            {"deadline": "2026-03-01"}, "2026-04-02",
        )
        assert "🚨 D+" in result

    def test_imminent_deadline(self, dashboard):
        result = dashboard._format_deadline(
            {"deadline": "2026-04-04"}, "2026-04-02",
        )
        assert "⚠️ D-2" in result


class TestKPIFormat:
    """KPI 포맷 테스트."""

    def test_no_metric(self, dashboard):
        result = dashboard._format_kpi({})
        assert result == ""

    def test_with_kpi(self, dashboard):
        result = dashboard._format_kpi({
            "kpi_metric": "signups",
            "kpi_target": 30000,
            "kpi_current": 15000,
            "kpi_unit": "명",
        })
        assert result == "(15000/30000명)"

    def test_kpi_no_current(self, dashboard):
        result = dashboard._format_kpi({
            "kpi_metric": "signups",
            "kpi_target": 30000,
        })
        assert result == "(0/30000)"

    def test_kpi_float_to_int(self, dashboard):
        result = dashboard._format_kpi({
            "kpi_metric": "rate",
            "kpi_target": 40.0,
            "kpi_current": 32.0,
            "kpi_unit": "%",
        })
        assert result == "(32/40%)"


class TestSummary:
    """요약 통계 테스트."""

    @pytest.mark.asyncio
    async def test_summary_content(self, db, tracker, dashboard):
        """요약 통계 포맷."""
        await db.initialize()
        await _setup_full_hierarchy(db, tracker)

        result = await dashboard.generate_full_dashboard(date="2026-04-02")

        assert "전체 진척률:" in result
        assert "Objective" in result
        assert "긴급 알림" in result
