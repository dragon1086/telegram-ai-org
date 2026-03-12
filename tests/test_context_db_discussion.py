"""ContextDB Discussion CRUD 테스트 — Task 2.1."""
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
        _db = ContextDB(db_path=Path(tmp) / "test.db")
        await _db.initialize()
        yield _db


@pytest.mark.asyncio
async def test_create_discussion(db):
    disc = await db.create_discussion(
        "D-001", "아키텍처 선택",
        participants=["aiorg_engineering_bot", "aiorg_design_bot"],
    )
    assert disc["id"] == "D-001"
    assert disc["status"] == "open"
    assert disc["current_round"] == 1
    assert len(disc["participants"]) == 2


@pytest.mark.asyncio
async def test_get_discussion(db):
    await db.create_discussion("D-002", "DB 설계", participants=["eng", "ops"])
    disc = await db.get_discussion("D-002")
    assert disc is not None
    assert disc["topic"] == "DB 설계"
    assert disc["participants"] == ["eng", "ops"]


@pytest.mark.asyncio
async def test_get_discussion_not_found(db):
    assert await db.get_discussion("nonexistent") is None


@pytest.mark.asyncio
async def test_add_discussion_message(db):
    await db.create_discussion("D-003", "topic", participants=["eng"])
    msg = await db.add_discussion_message(
        "D-003", "PROPOSE", "topic", "마이크로서비스 제안", "eng", 1
    )
    assert msg["msg_type"] == "PROPOSE"
    assert msg["round_num"] == 1


@pytest.mark.asyncio
async def test_get_discussion_messages(db):
    await db.create_discussion("D-004", "topic", participants=["eng", "design"])
    await db.add_discussion_message("D-004", "PROPOSE", "topic", "제안A", "eng", 1)
    await db.add_discussion_message("D-004", "COUNTER", "topic", "반대B", "design", 1)
    await db.add_discussion_message("D-004", "OPINION", "topic", "의견C", "eng", 2)

    all_msgs = await db.get_discussion_messages("D-004")
    assert len(all_msgs) == 3

    round1 = await db.get_discussion_messages("D-004", round_num=1)
    assert len(round1) == 2

    round2 = await db.get_discussion_messages("D-004", round_num=2)
    assert len(round2) == 1


@pytest.mark.asyncio
async def test_check_convergence_no_counter(db):
    """COUNTER 없으면 수렴."""
    await db.create_discussion("D-005", "topic", participants=["eng", "design"])
    await db.add_discussion_message("D-005", "PROPOSE", "topic", "제안", "eng", 1)
    await db.add_discussion_message("D-005", "OPINION", "topic", "동의", "design", 1)
    assert await db.check_convergence("D-005") is True


@pytest.mark.asyncio
async def test_check_convergence_with_counter(db):
    """COUNTER 있으면 비수렴."""
    await db.create_discussion("D-006", "topic", participants=["eng", "design"])
    await db.add_discussion_message("D-006", "PROPOSE", "topic", "제안", "eng", 1)
    await db.add_discussion_message("D-006", "COUNTER", "topic", "반대", "design", 1)
    assert await db.check_convergence("D-006") is False


@pytest.mark.asyncio
async def test_check_convergence_empty_round(db):
    """메시지 없는 라운드는 비수렴."""
    await db.create_discussion("D-007", "topic", participants=["eng"])
    assert await db.check_convergence("D-007") is False


@pytest.mark.asyncio
async def test_update_discussion_status(db):
    await db.create_discussion("D-008", "topic", participants=["eng"])
    updated = await db.update_discussion_status("D-008", "decided", decision="최종 결정")
    assert updated["status"] == "decided"
    assert updated["decision"] == "최종 결정"


@pytest.mark.asyncio
async def test_advance_round(db):
    await db.create_discussion("D-009", "topic", participants=["eng"])
    new_round = await db.advance_discussion_round("D-009")
    assert new_round == 2
    new_round = await db.advance_discussion_round("D-009")
    assert new_round == 3


@pytest.mark.asyncio
async def test_get_active_discussions(db):
    await db.create_discussion("D-010", "active", participants=["eng"])
    await db.create_discussion("D-011", "closed", participants=["design"])
    await db.update_discussion_status("D-011", "decided")

    active = await db.get_active_discussions()
    assert len(active) == 1
    assert active[0]["id"] == "D-010"
