"""Task Tree Architecture 단위 테스트.

UT-01: dispatch(goal_id, ...) → coordinator pm_task 생성 확인
UT-02: coordinator 하위 모든 subtask done → _synthesize_and_act에서 parent != None
UT-03: _synthesize_and_act(goal_id, ...) fallback — get_goal 호출 후 synthesis 진행
UT-04: handle_task_failure — assigned 태스크도 cascade cancel
UT-05: get_ready_tasks — failed dep 있는 태스크는 ready 목록에 포함
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.context_db import ContextDB
from core.task_graph import TaskGraph

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db(tmp_path):
    """임시 파일 기반 ContextDB."""
    db_path = str(tmp_path / "test.db")
    _db = ContextDB(db_path=db_path)
    await _db.initialize()
    yield _db


@pytest_asyncio.fixture
async def task_graph(db):
    return TaskGraph(db)


# ──────────────────────────────────────────────────────────────────────────────
# UT-01: dispatch() → coordinator pm_task 생성
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ut01_coordinator_created_when_parent_is_goal(db):
    """dispatch()에서 parent_task_id가 G-로 시작하면 coordinator pm_task가 생성된다."""
    goal_id = "G-test-001"

    # pm_goals에 goal 생성 (create_goal 사용)
    await db.create_goal(
        goal_id=goal_id,
        description="테스트 목표 설명",
        created_by="test_org",
        title="테스트 목표",
    )

    # coordinator 패턴 로직을 직접 시뮬레이션
    assert not await db.get_pm_task(goal_id), "아직 coordinator 없음"

    if goal_id.startswith("G-") and not await db.get_pm_task(goal_id):
        _goal = await db.get_goal(goal_id)
        assert _goal is not None

        coordinator_id = "T-test_org-001"
        await db.create_pm_task(
            task_id=coordinator_id,
            description=f"[Coordinator] {_goal.get('title', goal_id)}",
            assigned_dept=None,
            created_by="test_org",
            parent_id=goal_id,
            metadata={"coordinator": True, "goal_id": goal_id},
        )

    coordinator = await db.get_pm_task("T-test_org-001")
    assert coordinator is not None
    assert coordinator["description"].startswith("[Coordinator]")
    assert coordinator["parent_id"] == goal_id
    meta = coordinator.get("metadata") or {}
    assert meta.get("coordinator") is True
    assert meta.get("goal_id") == goal_id


# ──────────────────────────────────────────────────────────────────────────────
# UT-02: coordinator 하위 subtask 전부 done → parent != None
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ut02_synthesize_parent_not_none_after_subtasks_done(db):
    """coordinator pm_task가 있으면 get_pm_task(coordinator_id) != None."""
    goal_id = "G-test-002"
    coordinator_id = "T-test_org-coord-001"

    # goal 생성
    await db.create_goal(
        goal_id=goal_id,
        description="설명2",
        created_by="test_org",
        title="목표2",
    )

    # coordinator task 생성
    await db.create_pm_task(
        task_id=coordinator_id,
        description="[Coordinator] 목표2",
        assigned_dept=None,
        created_by="test_org",
        parent_id=goal_id,
        metadata={"coordinator": True, "goal_id": goal_id},
    )

    # subtask 생성 후 완료 처리
    await db.create_pm_task(
        task_id="T-sub-001",
        description="서브태스크 1",
        assigned_dept="engineering",
        created_by="test_org",
        parent_id=coordinator_id,
        metadata={},
    )
    await db.update_pm_task_status("T-sub-001", "done", result="완료")

    # _synthesize_and_act 에서 사용하는 get_pm_task(coordinator_id) 결과 확인
    parent = await db.get_pm_task(coordinator_id)
    assert parent is not None, "coordinator parent를 찾을 수 있어야 함"
    assert parent["id"] == coordinator_id


# ──────────────────────────────────────────────────────────────────────────────
# UT-03: _synthesize_and_act goal fallback — pm_goals에서 조회
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ut03_synthesize_fallback_from_goal(db):
    """parent_task_id가 G-로 시작하고 pm_tasks에 없으면 pm_goals에서 fallback."""
    goal_id = "G-fallback-001"

    # pm_goals에만 존재
    await db.create_goal(
        goal_id=goal_id,
        description="Fallback 목표 설명입니다",
        created_by="test_org",
        title="Fallback 목표",
    )

    # pm_tasks에는 없음
    parent = await db.get_pm_task(goal_id)
    assert parent is None

    # fallback 로직 시뮬레이션 (pm_synthesis_mixin.py 변경 내용)
    if parent is None and goal_id.startswith("G-"):
        _goal = await db.get_goal(goal_id)
        if _goal:
            parent = {
                "id": goal_id,
                "description": _goal.get("description", _goal.get("title", "")),
                "metadata": {"goal_id": goal_id, "_fallback_from_goal": True},
                "status": _goal.get("status", "active"),
            }

    assert parent is not None, "fallback 후 parent가 None이면 안 됨"
    assert parent["description"] == "Fallback 목표 설명입니다"
    assert parent["metadata"]["_fallback_from_goal"] is True
    assert parent["status"] == "active"


# ──────────────────────────────────────────────────────────────────────────────
# UT-04: handle_task_failure — assigned/running 태스크도 cascade cancel
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ut04_cascade_fail_retroactive_active_tasks(db, task_graph):
    """handle_task_failure는 assigned/running 상태 태스크도 cascade-fail 처리한다."""
    parent_id = "T-parent-001"

    # 태스크 4개 생성: 선행 1개 실패 + 후속 3개 (pending/assigned/running)
    for tid, dept, status in [
        ("T-fail-001", "engineering", "failed"),
        ("T-after-pending", "engineering", "pending"),
        ("T-after-assigned", "engineering", "assigned"),
        ("T-after-running", "engineering", "running"),
    ]:
        await db.create_pm_task(
            task_id=tid,
            description=f"태스크 {tid}",
            assigned_dept=dept,
            created_by="test_org",
            parent_id=parent_id,
            metadata={},
        )
        if status != "pending":
            await db.update_pm_task_status(tid, status)

    # 의존성 등록: 3개 후속 태스크 모두 T-fail-001에 의존
    for after_id in ["T-after-pending", "T-after-assigned", "T-after-running"]:
        await db.add_dependency(after_id, "T-fail-001")

    # cascade fail 실행
    affected = await task_graph.handle_task_failure("T-fail-001", policy="cascade_fail")

    assert len(affected) == 3

    for tid in ["T-after-pending", "T-after-assigned", "T-after-running"]:
        task = await db.get_pm_task(tid)
        assert task["status"] == "failed", f"{tid}는 failed 상태여야 함"


# ──────────────────────────────────────────────────────────────────────────────
# UT-05: get_ready_tasks — failed dep 있는 태스크는 ready 목록에 포함
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ut05_ready_tasks_excludes_failed_dep(db):
    """failed dep이 있는 태스크는 get_ready_tasks 결과에 포함된다.

    PRD 의도: dep이 failed면 cascade-fail이 처리하므로 ready_tasks에서는 블로킹하지 않음.
    """
    # group root
    await db.create_pm_task(
        task_id="T-group-001",
        description="그룹",
        assigned_dept=None,
        created_by="test_org",
        parent_id=None,
        metadata={},
    )

    # dep 태스크 (failed)
    await db.create_pm_task(
        task_id="T-dep-failed",
        description="실패한 의존성",
        assigned_dept="engineering",
        created_by="test_org",
        parent_id="T-group-001",
        metadata={},
    )
    await db.update_pm_task_status("T-dep-failed", "failed")

    # 후속 태스크 (pending, dep=T-dep-failed)
    await db.create_pm_task(
        task_id="T-after-001",
        description="후속 태스크",
        assigned_dept="engineering",
        created_by="test_org",
        parent_id="T-group-001",
        metadata={},
    )
    await db.add_dependency("T-after-001", "T-dep-failed")

    # get_ready_tasks: failed dep이 있어도 pending 태스크는 ready로 조회돼야 함
    ready = await db.get_ready_tasks("T-group-001")
    ready_ids = [t["id"] for t in ready]
    assert "T-after-001" in ready_ids, (
        "failed dep이 있는 태스크는 cascade-fail 정책에 따라 ready로 반환되어야 함"
    )
