"""ContextDB PM 태스크 CRUD 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
import tempfile

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "test.db")
        await cdb.initialize()
        yield cdb


@pytest.mark.asyncio
async def test_create_and_get_pm_task(db):
    result = await db.create_pm_task("T-pm-001", "test task", "eng", "pm")
    assert result["id"] == "T-pm-001"
    assert result["status"] == "pending"
    fetched = await db.get_pm_task("T-pm-001")
    assert fetched is not None
    assert fetched["description"] == "test task"


@pytest.mark.asyncio
async def test_update_pm_task_status(db):
    await db.create_pm_task("T-pm-001", "test", "eng", "pm")
    updated = await db.update_pm_task_status("T-pm-001", "done", result="완료")
    assert updated["status"] == "done"
    assert updated["result"] == "완료"


@pytest.mark.asyncio
async def test_get_nonexistent_task(db):
    result = await db.get_pm_task("T-pm-999")
    assert result is None


@pytest.mark.asyncio
async def test_get_subtasks(db):
    await db.create_pm_task("T-pm-001", "parent", None, "pm")
    await db.create_pm_task("T-pm-002", "child1", "eng", "pm", parent_id="T-pm-001")
    await db.create_pm_task("T-pm-003", "child2", "design", "pm", parent_id="T-pm-001")
    children = await db.get_subtasks("T-pm-001")
    assert len(children) == 2
    assert {c["id"] for c in children} == {"T-pm-002", "T-pm-003"}


@pytest.mark.asyncio
async def test_add_dependency_and_get_ready(db):
    await db.create_pm_task("T-pm-001", "parent", None, "pm")
    await db.create_pm_task("T-pm-002", "first", "eng", "pm", parent_id="T-pm-001")
    await db.create_pm_task("T-pm-003", "second", "design", "pm", parent_id="T-pm-001")
    await db.add_dependency("T-pm-003", "T-pm-002")
    # T-pm-002 has no deps -> ready, T-pm-003 depends on T-pm-002 -> not ready
    ready = await db.get_ready_tasks("T-pm-001")
    assert len(ready) == 1
    assert ready[0]["id"] == "T-pm-002"


@pytest.mark.asyncio
async def test_dependency_resolved_makes_task_ready(db):
    await db.create_pm_task("T-pm-001", "parent", None, "pm")
    await db.create_pm_task("T-pm-002", "first", "eng", "pm", parent_id="T-pm-001")
    await db.create_pm_task("T-pm-003", "second", "design", "pm", parent_id="T-pm-001")
    await db.add_dependency("T-pm-003", "T-pm-002")
    await db.update_pm_task_status("T-pm-002", "done")
    ready = await db.get_ready_tasks("T-pm-001")
    assert len(ready) == 1
    assert ready[0]["id"] == "T-pm-003"


@pytest.mark.asyncio
async def test_create_pm_task_with_parent(db):
    await db.create_pm_task("T-pm-001", "parent", None, "pm")
    child = await db.create_pm_task("T-pm-002", "child", "eng", "pm", parent_id="T-pm-001")
    assert child["parent_id"] == "T-pm-001"
