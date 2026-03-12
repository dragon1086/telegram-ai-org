"""DiscussionManager 단위 테스트 — Task 2.2."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.discussion import DiscussionManager
from core.message_bus import MessageBus


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "test.db")
        await cdb.initialize()
        yield cdb


@pytest.fixture
def send_fn():
    return AsyncMock()


@pytest.fixture
def bus():
    return MessageBus()


@pytest.mark.asyncio
async def test_start_discussion(db, send_fn, bus):
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    disc = await mgr.start_discussion(
        topic="아키텍처",
        initial_proposal="마이크로서비스 제안",
        from_dept="aiorg_engineering_bot",
        participants=["aiorg_engineering_bot", "aiorg_design_bot"],
        chat_id=123,
    )
    assert disc["id"] == "D-pm-001"
    assert disc["status"] == "open"
    assert disc["current_round"] == 1
    send_fn.assert_awaited_once()
    # PROPOSE 메시지 자동 등록 확인
    msgs = await db.get_discussion_messages("D-pm-001")
    assert len(msgs) == 1
    assert msgs[0]["msg_type"] == "PROPOSE"


@pytest.mark.asyncio
async def test_add_counter_message(db, send_fn, bus):
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="DB", initial_proposal="PostgreSQL",
        from_dept="eng", participants=["eng", "ops"],
    )
    msg = await mgr.add_message("D-pm-001", "COUNTER", "MongoDB가 더 적합", "ops")
    assert msg is not None
    assert msg["msg_type"] == "COUNTER"


@pytest.mark.asyncio
async def test_add_opinion_message(db, send_fn, bus):
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="UI", initial_proposal="React",
        from_dept="eng", participants=["eng", "design"],
    )
    msg = await mgr.add_message("D-pm-001", "OPINION", "React 동의", "design")
    assert msg is not None
    assert msg["msg_type"] == "OPINION"


@pytest.mark.asyncio
async def test_convergence_detected(db, send_fn, bus):
    """COUNTER 없으면 수렴 감지."""
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="API", initial_proposal="REST",
        from_dept="eng", participants=["eng", "design"],
        chat_id=123,
    )
    # OPINION만 추가 (COUNTER 없음) → 수렴
    await mgr.add_message("D-pm-001", "OPINION", "REST 동의", "design", chat_id=123)
    disc = await db.get_discussion("D-pm-001")
    assert disc["status"] == "converging"


@pytest.mark.asyncio
async def test_no_convergence_with_counter(db, send_fn, bus):
    """COUNTER 있으면 수렴 안 됨."""
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="API", initial_proposal="REST",
        from_dept="eng", participants=["eng", "design"],
    )
    await mgr.add_message("D-pm-001", "COUNTER", "GraphQL이 나음", "design")
    disc = await db.get_discussion("D-pm-001")
    assert disc["status"] == "open"  # 아직 open


@pytest.mark.asyncio
async def test_force_decision(db, send_fn, bus):
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="배포", initial_proposal="Docker",
        from_dept="ops", participants=["ops", "eng"],
    )
    result = await mgr.force_decision("D-pm-001", "Docker + K8s", chat_id=123)
    assert result is not None
    assert result["status"] == "decided"
    assert result["decision"] == "Docker + K8s"
    # DECISION 메시지 기록 확인
    msgs = await db.get_discussion_messages("D-pm-001")
    decision_msgs = [m for m in msgs if m["msg_type"] == "DECISION"]
    assert len(decision_msgs) == 1


@pytest.mark.asyncio
async def test_decision_via_add_message(db, send_fn, bus):
    """add_message에 DECISION 전달 시 force_decision으로 위임."""
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="언어", initial_proposal="Python",
        from_dept="eng", participants=["eng"],
    )
    result = await mgr.add_message("D-pm-001", "DECISION", "Python 확정", "pm")
    assert result is not None
    assert result["status"] == "decided"


@pytest.mark.asyncio
async def test_advance_round(db, send_fn, bus):
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="테스트", initial_proposal="TDD",
        from_dept="eng", participants=["eng"],
        chat_id=123,
    )
    new_round = await mgr.advance_round("D-pm-001", chat_id=123)
    assert new_round == 2


@pytest.mark.asyncio
async def test_advance_round_timeout(db, send_fn, bus):
    """max_rounds 초과 시 타임아웃."""
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="테스트", initial_proposal="TDD",
        from_dept="eng", participants=["eng"],
    )
    # max_rounds=3이므로 3번째에서 타임아웃
    await mgr.advance_round("D-pm-001")  # round 2
    await mgr.advance_round("D-pm-001")  # round 3
    result = await mgr.advance_round("D-pm-001")  # 초과 → -1
    assert result == -1
    disc = await db.get_discussion("D-pm-001")
    assert disc["status"] == "timed_out"


@pytest.mark.asyncio
async def test_message_to_closed_discussion(db, send_fn, bus):
    """종료된 토론에 메시지 추가 불가."""
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="닫힌토론", initial_proposal="제안",
        from_dept="eng", participants=["eng"],
    )
    await mgr.force_decision("D-pm-001", "결정")
    result = await mgr.add_message("D-pm-001", "COUNTER", "반대", "design")
    assert result is None


@pytest.mark.asyncio
async def test_invalid_msg_type_rejected(db, send_fn, bus):
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    await mgr.start_discussion(
        topic="t", initial_proposal="p",
        from_dept="eng", participants=["eng"],
    )
    result = await mgr.add_message("D-pm-001", "INVALID", "내용", "eng")
    assert result is None


@pytest.mark.asyncio
async def test_message_to_nonexistent_discussion(db, send_fn, bus):
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    result = await mgr.add_message("D-nonexistent", "PROPOSE", "내용", "eng")
    assert result is None


@pytest.mark.asyncio
async def test_discussion_id_increments(db, send_fn, bus):
    mgr = DiscussionManager(db, send_fn, bus, org_id="pm")
    d1 = await mgr.start_discussion("t1", "p1", "eng", ["eng"])
    d2 = await mgr.start_discussion("t2", "p2", "eng", ["eng"])
    assert d1["id"] == "D-pm-001"
    assert d2["id"] == "D-pm-002"
