"""Tests for /history and /stats command features."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

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
async def test_get_recent_pm_tasks_empty(db):
    """이력 없을 때 빈 리스트 반환."""
    result = await db.get_recent_pm_tasks(10)
    assert result == []


@pytest.mark.asyncio
async def test_get_recent_pm_tasks_order(db):
    """updated_at DESC 순으로 반환하며 limit 준수."""
    await db.create_pm_task("T-001", "first task", "eng", "pm")
    await db.create_pm_task("T-002", "second task", "design", "pm")
    await db.create_pm_task("T-003", "third task", "growth", "pm")
    # 상태 업데이트해 updated_at 순서 확정
    await db.update_pm_task_status("T-001", "done")
    await db.update_pm_task_status("T-002", "running")
    await db.update_pm_task_status("T-003", "assigned")

    tasks = await db.get_recent_pm_tasks(10)
    assert len(tasks) == 3
    # 가장 최근 업데이트가 첫 번째여야 함
    assert tasks[0]["id"] == "T-003"

    # limit 테스트
    limited = await db.get_recent_pm_tasks(2)
    assert len(limited) == 2


@pytest.mark.asyncio
async def test_get_recent_pm_tasks_fields(db):
    """반환 dict에 필요한 필드가 포함되어야 함."""
    await db.create_pm_task("T-001", "hello world task", "eng", "pm")
    tasks = await db.get_recent_pm_tasks(5)
    assert len(tasks) == 1
    t = tasks[0]
    assert "id" in t
    assert "description" in t
    assert "assigned_dept" in t
    assert "status" in t
    assert "created_at" in t
    assert "updated_at" in t
    assert t["description"] == "hello world task"
    assert t["assigned_dept"] == "eng"


@pytest.mark.asyncio
async def test_get_all_bot_performance_empty(db):
    """성과 데이터 없을 때 빈 리스트 반환."""
    result = await db.get_all_bot_performance()
    assert result == []


@pytest.mark.asyncio
async def test_get_all_bot_performance_with_data(db):
    """record_bot_task_completion 후 get_all_bot_performance가 데이터를 반환."""
    await db.create_pm_task("T-001", "task1", "aiorg_engineering_bot", "pm")
    await db.record_bot_task_completion("aiorg_engineering_bot", success=True, latency_sec=1.5)
    await db.record_bot_task_completion("aiorg_engineering_bot", success=True, latency_sec=2.5)
    await db.record_bot_task_completion("aiorg_growth_bot", success=False, latency_sec=3.0)

    perf = await db.get_all_bot_performance()
    assert len(perf) == 2

    bot_ids = {p["bot_id"] for p in perf}
    assert "aiorg_engineering_bot" in bot_ids
    assert "aiorg_growth_bot" in bot_ids

    eng = next(p for p in perf if p["bot_id"] == "aiorg_engineering_bot")
    assert eng["task_count"] == 2
    assert eng["success_count"] == 2
