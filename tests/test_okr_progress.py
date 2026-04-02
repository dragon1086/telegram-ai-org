"""OKR 계층 진척률 집계 테스트 (Phase 1.3)."""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.context_db import ContextDB
from core.goal_tracker import GoalTracker, GoalType


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


@pytest.mark.asyncio
async def test_task_self_progress(db, tracker):
    """Task는 자체 progress 반환."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="o", deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="KR", description="kr",
        parent_objective_id=obj_id, deadline="2026-06-30",
    )
    task_id = await tracker.start_goal(
        title="Task1", description="t",
        goal_type=GoalType.TASK, parent_goal_id=kr_id,
    )
    # 수동으로 progress 설정
    await db.update_goal(task_id, progress=0.7)
    progress = await tracker.calculate_progress(task_id)
    assert abs(progress - 0.7) < 0.01


@pytest.mark.asyncio
async def test_initiative_averages_tasks(db, tracker):
    """Initiative는 하위 Task들의 평균 progress."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="o", deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="KR", description="kr",
        parent_objective_id=obj_id, deadline="2026-06-30",
    )
    init_id = await tracker.create_initiative(
        title="Init", description="init",
        parent_kr_id=kr_id, deadline="2026-05-31",
    )
    t1 = await tracker.start_goal(
        title="T1", description="t1",
        goal_type=GoalType.TASK, parent_goal_id=init_id,
    )
    t2 = await tracker.start_goal(
        title="T2", description="t2",
        goal_type=GoalType.TASK, parent_goal_id=init_id,
    )
    await db.update_goal(t1, progress=0.8)
    await db.update_goal(t2, progress=0.4)

    progress = await tracker.calculate_progress(init_id)
    assert abs(progress - 0.6) < 0.01  # (0.8 + 0.4) / 2


@pytest.mark.asyncio
async def test_kr_uses_kpi(db, tracker):
    """KR은 KPI 기반 진척률 사용 (하위 목표보다 우선)."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="o", deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="KR", description="kr",
        parent_objective_id=obj_id, deadline="2026-06-30",
        kpi_metric="mau", kpi_target=100000,
    )
    await tracker.update_kpi(kr_id, kpi_current=30000)

    progress = await tracker.calculate_progress(kr_id)
    assert abs(progress - 0.3) < 0.01


@pytest.mark.asyncio
async def test_kr_without_kpi_uses_children(db, tracker):
    """KPI 없는 KR은 하위 Initiative 평균 사용."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="o", deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="KR", description="kr",
        parent_objective_id=obj_id, deadline="2026-06-30",
    )
    init1 = await tracker.create_initiative(
        title="Init1", description="i1",
        parent_kr_id=kr_id,
    )
    init2 = await tracker.create_initiative(
        title="Init2", description="i2",
        parent_kr_id=kr_id,
    )
    # Initiative에 직접 progress 설정 (하위 Task 없음)
    await db.update_goal(init1, progress=1.0)
    await db.update_goal(init2, progress=0.5)

    progress = await tracker.calculate_progress(kr_id)
    assert abs(progress - 0.75) < 0.01  # (1.0 + 0.5) / 2


@pytest.mark.asyncio
async def test_objective_weighted_average(db, tracker):
    """Objective는 KR들의 가중 평균."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="o", deadline="2026-12-31",
    )
    kr1 = await tracker.create_key_result(
        title="KR1", description="kr1",
        parent_objective_id=obj_id, deadline="2026-06-30",
        kpi_metric="mau", kpi_target=100000,
        weight=0.7,
    )
    kr2 = await tracker.create_key_result(
        title="KR2", description="kr2",
        parent_objective_id=obj_id, deadline="2026-09-30",
        kpi_metric="revenue", kpi_target=50000,
        weight=0.3,
    )
    await tracker.update_kpi(kr1, kpi_current=50000)  # 50%
    await tracker.update_kpi(kr2, kpi_current=25000)  # 50%

    progress = await tracker.calculate_progress(obj_id)
    # (0.5 * 0.7 + 0.5 * 0.3) / (0.7 + 0.3) = 0.5
    assert abs(progress - 0.5) < 0.01


@pytest.mark.asyncio
async def test_objective_unequal_weights(db, tracker):
    """Objective 가중 평균 — 비균등 가중치."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="o", deadline="2026-12-31",
    )
    kr1 = await tracker.create_key_result(
        title="KR1", description="kr1",
        parent_objective_id=obj_id, deadline="2026-06-30",
        kpi_metric="mau", kpi_target=100000,
        weight=0.8,
    )
    kr2 = await tracker.create_key_result(
        title="KR2", description="kr2",
        parent_objective_id=obj_id, deadline="2026-09-30",
        kpi_metric="nps", kpi_target=80,
        weight=0.2,
    )
    await tracker.update_kpi(kr1, kpi_current=100000)  # 100%
    await tracker.update_kpi(kr2, kpi_current=40)  # 50%

    progress = await tracker.calculate_progress(obj_id)
    # (1.0 * 0.8 + 0.5 * 0.2) / (0.8 + 0.2) = 0.9
    assert abs(progress - 0.9) < 0.01


@pytest.mark.asyncio
async def test_update_hierarchy_progress(db, tracker):
    """update_hierarchy_progress: 하위→상위 재귀 업데이트."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="o", deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="KR", description="kr",
        parent_objective_id=obj_id, deadline="2026-06-30",
        kpi_metric="users", kpi_target=1000,
    )
    await tracker.update_kpi(kr_id, kpi_current=600)

    # 하위부터 업데이트 → 부모도 자동 업데이트
    await tracker.update_hierarchy_progress(kr_id)

    kr = await db.get_goal(kr_id)
    assert abs(kr["progress"] - 0.6) < 0.01

    obj = await db.get_goal(obj_id)
    assert abs(obj["progress"] - 0.6) < 0.01  # KR 1개 → 동일


@pytest.mark.asyncio
async def test_no_children_returns_self_progress(db, tracker):
    """하위 목표 없는 경우 자체 progress 반환."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="o", deadline="2026-12-31",
    )
    await db.update_goal(obj_id, progress=0.33)

    progress = await tracker.calculate_progress(obj_id)
    assert abs(progress - 0.33) < 0.01


@pytest.mark.asyncio
async def test_nonexistent_goal(db, tracker):
    """존재하지 않는 goal_id → 0.0 반환."""
    await db.initialize()
    progress = await tracker.calculate_progress("G-nonexistent")
    assert progress == 0.0
