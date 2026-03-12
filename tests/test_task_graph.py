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
