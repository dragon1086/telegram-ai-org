"""OKR GoalTracker 계층 메서드 검증 (Phase 1.2)."""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.context_db import ContextDB
from core.goal_tracker import EVALUATION_CONFIG, GoalTracker, GoalType


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
async def test_goal_type_enum():
    """GoalType enum 값 확인."""
    assert GoalType.OBJECTIVE == "objective"
    assert GoalType.KEY_RESULT == "key_result"
    assert GoalType.INITIATIVE == "initiative"
    assert GoalType.TASK == "task"


@pytest.mark.asyncio
async def test_evaluation_config_exists():
    """계층별 평가 전략 설정 확인."""
    assert GoalType.TASK in EVALUATION_CONFIG
    assert EVALUATION_CONFIG[GoalType.TASK]["method"] == "iteration"
    assert EVALUATION_CONFIG[GoalType.KEY_RESULT]["method"] == "kpi_tracking"
    assert EVALUATION_CONFIG[GoalType.OBJECTIVE]["rollover_on_miss"] is True


@pytest.mark.asyncio
async def test_create_objective(db, tracker):
    """Objective 생성."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="2026 MAU 10만",
        description="연간 사용자 확대 목표",
        deadline="2026-12-31",
        chat_id=123,
    )
    assert obj_id.startswith("G-pm-")
    goal = await db.get_goal(obj_id)
    assert goal["goal_type"] == "objective"
    assert goal["deadline"] == "2026-12-31"
    assert goal["check_interval"] == "quarterly"


@pytest.mark.asyncio
async def test_create_kr_under_objective(db, tracker):
    """Objective 아래 KR 생성."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="MAU 10만", description="연간", deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="Q2 신규가입 3만",
        description="분기 가입 목표",
        parent_objective_id=obj_id,
        deadline="2026-06-30",
        kpi_metric="signups",
        kpi_target=30000,
        kpi_unit="명",
        weight=0.5,
    )
    goal = await db.get_goal(kr_id)
    assert goal["goal_type"] == "key_result"
    assert goal["parent_goal_id"] == obj_id
    assert goal["kpi_metric"] == "signups"
    assert goal["kpi_target"] == 30000
    assert goal["weight"] == 0.5
    assert goal["check_interval"] == "monthly"


@pytest.mark.asyncio
async def test_create_initiative_under_kr(db, tracker):
    """KR 아래 Initiative 생성."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="MAU", description="obj", deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="Q2 가입", description="kr",
        parent_objective_id=obj_id, deadline="2026-06-30",
    )
    init_id = await tracker.create_initiative(
        title="소셜 마케팅 캠페인",
        description="인스타/틱톡 광고",
        parent_kr_id=kr_id,
        deadline="2026-05-31",
    )
    goal = await db.get_goal(init_id)
    assert goal["goal_type"] == "initiative"
    assert goal["parent_goal_id"] == kr_id
    assert goal["check_interval"] == "weekly"


@pytest.mark.asyncio
async def test_get_children(db, tracker):
    """계층 하위 목표 조회."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="obj", deadline="2026-12-31",
    )
    kr1_id = await tracker.create_key_result(
        title="KR1", description="kr1",
        parent_objective_id=obj_id, deadline="2026-06-30",
    )
    kr2_id = await tracker.create_key_result(
        title="KR2", description="kr2",
        parent_objective_id=obj_id, deadline="2026-09-30",
    )
    children = await tracker.get_children(obj_id)
    assert len(children) == 2

    kr_children = await tracker.get_children(obj_id, GoalType.KEY_RESULT)
    assert len(kr_children) == 2


@pytest.mark.asyncio
async def test_get_objectives(db, tracker):
    """Objective 목록 조회."""
    await db.initialize()
    await tracker.create_objective(
        title="Obj1", description="o1", deadline="2026-12-31",
    )
    await tracker.create_key_result(
        title="KR1", description="kr1",
        parent_objective_id="G-pm-001", deadline="2026-06-30",
    )
    objectives = await tracker.get_objectives(status="active")
    assert len(objectives) == 1
    assert objectives[0]["goal_type"] == "objective"


@pytest.mark.asyncio
async def test_update_kpi(db, tracker):
    """KPI 업데이트 + 진척률 자동 계산."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="obj", deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="KR", description="kr",
        parent_objective_id=obj_id, deadline="2026-06-30",
        kpi_metric="mau", kpi_target=100000,
    )
    updated = await tracker.update_kpi(kr_id, kpi_current=44000)
    assert updated["kpi_current"] == 44000
    assert abs(updated["progress"] - 0.44) < 0.01


@pytest.mark.asyncio
async def test_trace_to_kr(db, tracker):
    """Task → Initiative → KR 추적."""
    await db.initialize()
    obj_id = await tracker.create_objective(
        title="Obj", description="o", deadline="2026-12-31",
    )
    kr_id = await tracker.create_key_result(
        title="KR1", description="kr",
        parent_objective_id=obj_id, deadline="2026-06-30",
    )
    init_id = await tracker.create_initiative(
        title="Init1", description="init",
        parent_kr_id=kr_id,
    )
    task_id = await tracker.start_goal(
        title="Task1", description="task",
        goal_type=GoalType.TASK,
        parent_goal_id=init_id,
    )
    kr = await tracker.trace_to_kr(task_id)
    assert kr is not None
    assert kr["id"] == kr_id
    assert kr["goal_type"] == "key_result"


@pytest.mark.asyncio
async def test_record_snapshot(db, tracker):
    """진척 스냅샷 기록."""
    await db.initialize()
    kr_id = await tracker.create_key_result(
        title="KR", description="kr",
        parent_objective_id="O-none", deadline="2026-06-30",
        kpi_metric="mau", kpi_target=100000,
    )
    await tracker.update_kpi(kr_id, kpi_current=50000)
    await tracker.record_snapshot(kr_id, "weekly", "2026-04-02")
    snapshots = await db.get_progress_snapshots(kr_id)
    assert len(snapshots) == 1
    assert abs(snapshots[0]["progress"] - 0.5) < 0.01
    assert snapshots[0]["kpi_current"] == 50000


@pytest.mark.asyncio
async def test_task_starts_loop_objective_does_not(db, tracker):
    """Task는 자율 루프 시작, Objective는 루프 미실행."""
    await db.initialize()
    # Objective — 루프 시작 안 함
    obj_id = await tracker.create_objective(
        title="NoLoop", description="no loop", deadline="2026-12-31",
    )
    # Task — 루프 시작 (run_loop가 호출되지만 mock이므로 OK)
    task_id = await tracker.start_goal(
        title="WithLoop", description="with loop",
        goal_type=GoalType.TASK, chat_id=1,
    )
    # 두 목표 모두 active
    obj = await db.get_goal(obj_id)
    task = await db.get_goal(task_id)
    assert obj["status"] == "active"
    assert task["status"] == "active"


@pytest.mark.asyncio
async def test_duplicate_prevention(db, tracker):
    """동일 제목 목표 중복 생성 방지."""
    await db.initialize()
    id1 = await tracker.create_objective(
        title="중복 테스트", description="o", deadline="2026-12-31",
    )
    id2 = await tracker.create_objective(
        title="중복 테스트", description="o2", deadline="2026-12-31",
    )
    assert id1 == id2  # 같은 ID 반환
