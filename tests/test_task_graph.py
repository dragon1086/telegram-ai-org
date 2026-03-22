"""TaskGraph 단위 테스트 — ContextDB 기반 의존성 DAG."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph


@pytest.fixture
async def setup():
    with tempfile.TemporaryDirectory() as tmp:
        db = ContextDB(Path(tmp) / "test.db")
        await db.initialize()
        graph = TaskGraph(db)
        yield db, graph


@pytest.mark.asyncio
async def test_linear_chain(setup):
    """A -> B -> C 선형 체인."""
    db, graph = setup
    await db.create_pm_task("T-pm-root", "root", None, "pm")
    await db.create_pm_task("T-pm-001", "A", "eng", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-002", "B", "design", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-003", "C", "ops", "pm", parent_id="T-pm-root")
    await graph.add_task("T-pm-001")
    await graph.add_task("T-pm-002", depends_on=["T-pm-001"])
    await graph.add_task("T-pm-003", depends_on=["T-pm-002"])
    ready = await graph.get_ready_tasks("T-pm-root")
    assert ready == ["T-pm-001"]


@pytest.mark.asyncio
async def test_parallel_fan_out(setup):
    """A 완료 후 B,C 병렬 실행."""
    db, graph = setup
    await db.create_pm_task("T-pm-root", "root", None, "pm")
    await db.create_pm_task("T-pm-001", "A", "product", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-002", "B", "eng", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-003", "C", "design", "pm", parent_id="T-pm-root")
    await graph.add_task("T-pm-001")
    await graph.add_task("T-pm-002", depends_on=["T-pm-001"])
    await graph.add_task("T-pm-003", depends_on=["T-pm-001"])
    newly_ready = await graph.mark_complete("T-pm-001")
    assert set(newly_ready) == {"T-pm-002", "T-pm-003"}


@pytest.mark.asyncio
async def test_diamond_dependency(setup):
    """A -> B,C -> D 다이아몬드."""
    db, graph = setup
    await db.create_pm_task("T-pm-root", "root", None, "pm")
    await db.create_pm_task("T-pm-A", "A", "product", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-B", "B", "eng", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-C", "C", "design", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-D", "D", "ops", "pm", parent_id="T-pm-root")
    await graph.add_task("T-pm-A")
    await graph.add_task("T-pm-B", depends_on=["T-pm-A"])
    await graph.add_task("T-pm-C", depends_on=["T-pm-A"])
    await graph.add_task("T-pm-D", depends_on=["T-pm-B", "T-pm-C"])
    # A 완료 -> B,C ready
    await graph.mark_complete("T-pm-A")
    # B 완료 -> D는 아직 (C가 남음)
    newly = await graph.mark_complete("T-pm-B")
    assert "T-pm-D" not in newly
    # C 완료 -> D ready
    newly = await graph.mark_complete("T-pm-C")
    assert "T-pm-D" in newly


@pytest.mark.asyncio
async def test_cycle_rejection(setup):
    """순환 의존성 감지."""
    db, graph = setup
    await db.create_pm_task("T-pm-root", "root", None, "pm")
    await db.create_pm_task("T-pm-A", "A", "eng", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-B", "B", "eng", "pm", parent_id="T-pm-root")
    await graph.add_task("T-pm-A")
    await graph.add_task("T-pm-B", depends_on=["T-pm-A"])
    with pytest.raises(ValueError, match="순환"):
        await graph.add_task("T-pm-A", depends_on=["T-pm-B"])


@pytest.mark.asyncio
async def test_no_deps_all_ready(setup):
    """의존성 없는 태스크는 모두 즉시 실행 가능."""
    db, graph = setup
    await db.create_pm_task("T-pm-root", "root", None, "pm")
    await db.create_pm_task("T-pm-001", "A", "eng", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-002", "B", "design", "pm", parent_id="T-pm-root")
    await graph.add_task("T-pm-001")
    await graph.add_task("T-pm-002")
    ready = await graph.get_ready_tasks("T-pm-root")
    assert set(ready) == {"T-pm-001", "T-pm-002"}


@pytest.mark.asyncio
async def test_blocked_task_not_ready_until_predecessor_completes(setup):
    """사전 등록 시나리오: deps 등록 직후 후행 태스크는 ready에 없고, 선행 완료 후에만 진입.

    레이스 컨디션 수정(cf42da4)의 핵심 — deps를 태스크 생성보다 먼저 등록해도
    get_ready_tasks가 올바르게 blocking을 유지하는지 검증한다.
    """
    db, graph = setup
    await db.create_pm_task("T-pm-root", "root", None, "pm")
    await db.create_pm_task("T-pm-001", "리서치", "research", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-002", "개발", "eng", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-003", "운영", "ops", "pm", parent_id="T-pm-root")

    # Step 0 순서 재현: deps 먼저 등록 (태스크 본문 생성 전)
    await graph.add_task("T-pm-001")
    await graph.add_task("T-pm-002", depends_on=["T-pm-001"])
    await graph.add_task("T-pm-003", depends_on=["T-pm-002"])

    # 의존성 등록 직후: 리서치(001)만 ready, 개발(002)·운영(003)은 blocking
    ready = await graph.get_ready_tasks("T-pm-root")
    assert ready == ["T-pm-001"], f"초기 ready={ready}, 리서치만 있어야 함"

    # 리서치 완료 → 개발만 unblock
    newly = await graph.mark_complete("T-pm-001")
    assert "T-pm-002" in newly
    assert "T-pm-003" not in newly

    # 개발 완료 → 운영 unblock
    newly = await graph.mark_complete("T-pm-002")
    assert "T-pm-003" in newly


@pytest.mark.asyncio
async def test_handle_task_failure_cascade_fail(setup):
    """선행 태스크 실패 시 후속 태스크가 cascade_fail 정책으로 'failed' 처리."""
    db, graph = setup
    await db.create_pm_task("T-pm-root", "root", None, "pm")
    await db.create_pm_task("T-pm-A", "리서치", "research", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-B", "개발", "eng", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-C", "운영", "ops", "pm", parent_id="T-pm-root")
    await graph.add_task("T-pm-A")
    await graph.add_task("T-pm-B", depends_on=["T-pm-A"])
    await graph.add_task("T-pm-C", depends_on=["T-pm-B"])

    # 리서치(A) 실패 → B, C cascade_fail
    await db.update_pm_task_status("T-pm-A", "failed")
    affected = await graph.handle_task_failure("T-pm-A", policy="cascade_fail")

    assert set(affected) == {"T-pm-B", "T-pm-C"}
    b_task = await db.get_pm_task("T-pm-B")
    c_task = await db.get_pm_task("T-pm-C")
    assert b_task["status"] == "failed"
    assert c_task["status"] == "failed"


@pytest.mark.asyncio
async def test_handle_task_failure_skip_policy(setup):
    """선행 태스크 실패 시 skip 정책으로 후속 태스크가 'skipped' 처리."""
    db, graph = setup
    await db.create_pm_task("T-pm-root", "root", None, "pm")
    await db.create_pm_task("T-pm-A", "리서치", "research", "pm", parent_id="T-pm-root")
    await db.create_pm_task("T-pm-B", "개발", "eng", "pm", parent_id="T-pm-root")
    await graph.add_task("T-pm-A")
    await graph.add_task("T-pm-B", depends_on=["T-pm-A"])

    await db.update_pm_task_status("T-pm-A", "failed")
    affected = await graph.handle_task_failure("T-pm-A", policy="skip")

    assert "T-pm-B" in affected
    b_task = await db.get_pm_task("T-pm-B")
    assert b_task["status"] == "skipped"
