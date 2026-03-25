"""Tests for BotBusinessRetro."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pytest_asyncio

from core.bot_business_retro import BotBusinessRetro


@pytest_asyncio.fixture
async def retro_with_data(tmp_path):
    from core.context_db import ContextDB
    db = ContextDB(db_path=str(tmp_path / "test.db"))
    await db.initialize()
    week = "2026-W11"
    # bot_high: 3 tasks, 3 success
    for _ in range(3):
        await db.record_bot_task_completion("bot_high", True, 5.0, week=week)
    # bot_mid: 2 tasks, 2 success
    for _ in range(2):
        await db.record_bot_task_completion("bot_mid", True, 5.0, week=week)
    # bot_low: 2 tasks, 1 success (50% rate → action item)
    await db.record_bot_task_completion("bot_low", True, 5.0, week=week)
    await db.record_bot_task_completion("bot_low", False, 5.0, week=week)
    return BotBusinessRetro(db), week


@pytest.mark.asyncio
async def test_generate_weekly_empty(tmp_path):
    from core.context_db import ContextDB
    db = ContextDB(db_path=str(tmp_path / "test.db"))
    await db.initialize()
    retro = BotBusinessRetro(db)
    result = await retro.generate_weekly()
    assert result == []


@pytest.mark.asyncio
async def test_generate_weekly_ranking(retro_with_data):
    retro, week = retro_with_data
    results = await retro.generate_weekly(week=week)
    assert len(results) == 3
    assert results[0]["bot_id"] == "bot_high"
    assert results[0]["peer_rank"] == 1
    assert results[2]["bot_id"] == "bot_low"
    assert results[2]["peer_rank"] == 3


@pytest.mark.asyncio
async def test_action_items_low_rate(retro_with_data):
    retro, week = retro_with_data
    results = await retro.generate_weekly(week=week)
    low_bot = next(r for r in results if r["bot_id"] == "bot_low")
    assert any("성공률 70% 미만" in item for item in low_bot["action_items"])


@pytest.mark.asyncio
async def test_format_telegram(retro_with_data):
    retro, week = retro_with_data
    results = await retro.generate_weekly(week=week)
    msg = retro.format_telegram(results)
    assert week in msg
    assert "bot_high" in msg
    assert "bot_mid" in msg
    assert "bot_low" in msg


@pytest.mark.asyncio
async def test_generate_weekly_no_deleted_bots(tmp_path):
    """Deleted bots (no data this week) don't appear in results."""
    from core.context_db import ContextDB
    db = ContextDB(db_path=str(tmp_path / "test.db"))
    await db.initialize()
    # Only record for old_week
    await db.record_bot_task_completion("old_bot", True, 5.0, week="2026-W01")
    retro = BotBusinessRetro(db)
    results = await retro.generate_weekly(week="2026-W11")
    assert results == []  # old_bot has no data for W11


def test_scheduler_has_retro_job(tmp_path):
    """OrgScheduler registers weekly_bot_business_retro job."""
    from core.scheduler import OrgScheduler
    # Just verify the method exists
    assert hasattr(OrgScheduler, "_weekly_bot_business_retro")
