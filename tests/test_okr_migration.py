"""OKR 마이그레이션 검증 테스트 (Phase 1.1)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.context_db import ContextDB


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_okr.db")


@pytest.fixture
def db(db_path):
    return ContextDB(db_path)


@pytest.mark.asyncio
async def test_migration_creates_okr_columns(db):
    """Migration 002: OKR 컬럼이 pm_goals에 추가되는지 확인."""
    await db.initialize()
    goal = await db.create_goal(
        goal_id="G-test-001",
        description="Test objective",
        created_by="pm",
        chat_id=123,
        goal_type="objective",
        deadline="2026-12-31",
        kpi_metric="mau",
        kpi_target=100000,
        kpi_current=50000,
        kpi_unit="명",
        weight=1.0,
    )
    assert goal["goal_type"] == "objective"
    assert goal["deadline"] == "2026-12-31"
    assert goal["kpi_metric"] == "mau"
    assert goal["kpi_target"] == 100000
    assert goal["kpi_current"] == 50000
    assert goal["kpi_unit"] == "명"
    assert goal["weight"] == 1.0
    assert goal["parent_goal_id"] is None
    assert goal["rollover_count"] == 0


@pytest.mark.asyncio
async def test_migration_creates_hierarchy(db):
    """계층 구조 (Objective → KR → Task) 생성 및 조회."""
    await db.initialize()
    # Objective
    await db.create_goal(
        goal_id="O-001", description="연간 목표",
        created_by="pm", chat_id=1, goal_type="objective",
        title="MAU 10만",
    )
    # KR under Objective
    await db.create_goal(
        goal_id="KR-001", description="분기 KR",
        created_by="pm", chat_id=1, goal_type="key_result",
        parent_goal_id="O-001", title="Q2 신규가입 3만",
        kpi_metric="signups", kpi_target=30000,
    )
    # Task under KR
    await db.create_goal(
        goal_id="T-001", description="주간 태스크",
        created_by="engineering", chat_id=1, goal_type="task",
        parent_goal_id="KR-001", title="랜딩페이지 개선",
    )
    # 하위 목표 조회
    children = await db.get_children_goals("O-001")
    assert len(children) == 1
    assert children[0]["id"] == "KR-001"

    kr_children = await db.get_children_goals("KR-001", goal_type="task")
    assert len(kr_children) == 1
    assert kr_children[0]["id"] == "T-001"


@pytest.mark.asyncio
async def test_migration_creates_snapshots_table(db):
    """Migration 003: progress_snapshots 테이블 생성 및 CRUD."""
    await db.initialize()
    await db.record_progress_snapshot(
        goal_id="KR-001", progress=0.44,
        snapshot_type="weekly", snapshot_date="2026-04-02",
        kpi_current=13200, notes="주간 점검",
    )
    # 중복 삽입 (upsert)
    await db.record_progress_snapshot(
        goal_id="KR-001", progress=0.50,
        snapshot_type="weekly", snapshot_date="2026-04-02",
        kpi_current=15000, notes="수정됨",
    )
    snapshots = await db.get_progress_snapshots("KR-001")
    assert len(snapshots) == 1  # upsert이므로 1건
    assert snapshots[0]["progress"] == 0.50
    assert snapshots[0]["kpi_current"] == 15000
    assert snapshots[0]["notes"] == "수정됨"


@pytest.mark.asyncio
async def test_migration_creates_evaluations_table(db):
    """Migration 004: performance_evaluations 테이블 CRUD."""
    await db.initialize()
    eval_id = await db.save_performance_evaluation(
        dept_id="engineering",
        period_start="2026-01-01",
        period_end="2026-03-31",
        period_type="quarterly",
        overall_score=82.5,
        grade="B",
        criteria_scores=json.dumps({"completion_rate": 0.85, "quality": 0.82}),
        strengths=json.dumps(["코드 품질", "디버깅"]),
        weaknesses=json.dumps(["협업 빈도"]),
        prompt_fragment="개발실 분기 진화 프롬프트",
    )
    assert eval_id > 0

    evals = await db.get_performance_evaluations(dept_id="engineering")
    assert len(evals) == 1
    assert evals[0]["overall_score"] == 82.5
    assert evals[0]["grade"] == "B"
    assert evals[0]["criteria_scores"]["completion_rate"] == 0.85
    assert "코드 품질" in evals[0]["strengths"]


@pytest.mark.asyncio
async def test_get_goals_by_type(db):
    """goal_type별 조회."""
    await db.initialize()
    await db.create_goal(
        goal_id="O-001", description="obj", created_by="pm",
        chat_id=1, goal_type="objective", title="Obj1",
    )
    await db.create_goal(
        goal_id="KR-001", description="kr", created_by="pm",
        chat_id=1, goal_type="key_result", title="KR1",
    )
    await db.create_goal(
        goal_id="T-001", description="task", created_by="pm",
        chat_id=1, goal_type="task", title="Task1",
    )
    objectives = await db.get_goals_by_type("objective")
    assert len(objectives) == 1
    assert objectives[0]["goal_type"] == "objective"

    tasks = await db.get_goals_by_type("task", status="active")
    assert len(tasks) == 1


@pytest.mark.asyncio
async def test_update_goal_okr_fields(db):
    """update_goal()에서 OKR 컬럼 업데이트."""
    await db.initialize()
    await db.create_goal(
        goal_id="KR-001", description="kr", created_by="pm",
        chat_id=1, goal_type="key_result", kpi_target=30000,
    )
    updated = await db.update_goal(
        "KR-001", kpi_current=15000, progress=0.5,
        status="active", deadline="2026-06-30",
    )
    assert updated["kpi_current"] == 15000
    assert updated["progress"] == 0.5
    assert updated["deadline"] == "2026-06-30"


@pytest.mark.asyncio
async def test_backward_compatibility(db):
    """기존 create_goal() 호출 방식이 여전히 작동하는지 확인."""
    await db.initialize()
    goal = await db.create_goal(
        goal_id="G-pm-001",
        description="기존 방식 테스트",
        created_by="pm",
        chat_id=123,
        max_iterations=10,
        title="레거시 목표",
    )
    assert goal["goal_type"] == "task"  # 기본값
    assert goal["parent_goal_id"] is None
    assert goal["kpi_target"] is None
    assert goal["progress"] == 0

    # get_goal도 새 컬럼 반환
    fetched = await db.get_goal("G-pm-001")
    assert fetched is not None
    assert fetched["goal_type"] == "task"


@pytest.mark.asyncio
async def test_idempotent_migration(db):
    """마이그레이션을 2번 실행해도 오류 없음."""
    await db.initialize()
    await db.initialize()  # 2번째 실행
    goal = await db.create_goal(
        goal_id="G-test-idem", description="idem",
        created_by="pm", chat_id=1, goal_type="objective",
    )
    assert goal["goal_type"] == "objective"
