"""Tests for bot_performance table in ContextDB."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    from core.context_db import ContextDB
    db_path = str(tmp_path / "test_context.db")
    ctx = ContextDB(db_path=db_path)
    await ctx.initialize()
    return ctx


@pytest.mark.asyncio
async def test_bot_performance_table_created(temp_db):
    async with aiosqlite.connect(temp_db.db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_performance'"
        )
        row = await cursor.fetchone()
    assert row is not None, "bot_performance table must exist after initialize()"


@pytest.mark.asyncio
async def test_record_and_get_bot_performance(temp_db):
    week = "2026-W11"
    await temp_db.record_bot_task_completion("bot_a", True, 10.0, week=week)
    await temp_db.record_bot_task_completion("bot_a", True, 20.0, week=week)
    await temp_db.record_bot_task_completion("bot_a", False, 30.0, week=week)

    result = await temp_db.get_bot_performance("bot_a", week=week)
    assert result is not None
    assert result["task_count"] == 3
    assert result["success_count"] == 2
    # avg_latency = (10 + 20 + 30) / 3 = 20.0 (within tolerance)
    assert abs(result["avg_latency_sec"] - 20.0) < 1.0


@pytest.mark.asyncio
async def test_get_all_bot_performance_ranking(temp_db):
    week = "2026-W11"
    await temp_db.record_bot_task_completion("bot_low", True, 5.0, week=week)
    await temp_db.record_bot_task_completion("bot_mid", True, 5.0, week=week)
    await temp_db.record_bot_task_completion("bot_mid", True, 5.0, week=week)
    await temp_db.record_bot_task_completion("bot_high", True, 5.0, week=week)
    await temp_db.record_bot_task_completion("bot_high", True, 5.0, week=week)
    await temp_db.record_bot_task_completion("bot_high", True, 5.0, week=week)

    all_perf = await temp_db.get_all_bot_performance(week=week)
    assert len(all_perf) == 3
    assert all_perf[0]["bot_id"] == "bot_high"
    assert all_perf[1]["bot_id"] == "bot_mid"
    assert all_perf[2]["bot_id"] == "bot_low"


@pytest.mark.asyncio
async def test_record_bot_perf_concurrent(temp_db):
    """Atomic upsert must handle 10 concurrent writes without race conditions."""
    week = "2026-W11"
    await asyncio.gather(*[
        temp_db.record_bot_task_completion("bot_x", True, 1.0, week=week)
        for _ in range(10)
    ])
    result = await temp_db.get_bot_performance("bot_x", week=week)
    assert result is not None
    assert result["task_count"] == 10
    assert result["success_count"] == 10
    assert abs(result["avg_latency_sec"] - 1.0) < 0.5


@pytest.mark.asyncio
async def test_new_bot_auto_creates_row(temp_db):
    """New bot gets a row on first task completion (no pre-registration needed)."""
    week = "2026-W11"
    await temp_db.record_bot_task_completion("brand_new_bot", True, 5.0, week=week)
    result = await temp_db.get_bot_performance("brand_new_bot", week=week)
    assert result is not None
    assert result["task_count"] == 1


@pytest.mark.asyncio
async def test_deleted_bot_data_preserved(temp_db):
    """Deleted bot's historical data remains queryable."""
    week = "2026-W10"
    await temp_db.record_bot_task_completion("old_bot", True, 5.0, week=week)
    # Even after "deletion" (no new writes), historical data accessible
    result = await temp_db.get_bot_performance("old_bot", week=week)
    assert result is not None
    assert result["task_count"] == 1
