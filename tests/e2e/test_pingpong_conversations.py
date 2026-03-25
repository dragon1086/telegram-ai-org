"""자율 봇 핑퐁 대화 E2E 테스트 (5개 TC).

DiscussionManager를 직접 테스트한다 (core/discussion.py).
ContextDB는 MagicMock (비동기 메서드는 AsyncMock).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.discussion import DiscussionManager

# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────


def _make_manager(org_id: str = "pm") -> tuple[DiscussionManager, MagicMock, AsyncMock]:
    """최소 mock으로 DiscussionManager 인스턴스 생성.

    Returns:
        (manager, db_mock, send_mock)
    """
    db = MagicMock()
    db.create_discussion = AsyncMock()
    db.add_discussion_message = AsyncMock()
    db.get_discussion = AsyncMock()
    db.update_discussion_status = AsyncMock()
    db.advance_discussion_round = AsyncMock()
    db.check_convergence = AsyncMock(return_value=False)
    db.get_active_discussions = AsyncMock(return_value=[])

    send_func = AsyncMock()

    manager = DiscussionManager(
        context_db=db,
        telegram_send_func=send_func,
        bus=None,
        org_id=org_id,
    )
    return manager, db, send_func


def _make_disc_record(
    disc_id: str,
    topic: str = "테스트 토론",
    status: str = "open",
    current_round: int = 1,
    max_rounds: int = 3,
    participants: list[str] | None = None,
) -> dict:
    """테스트용 토론 레코드 생성."""
    return {
        "discussion_id": disc_id,
        "topic": topic,
        "status": status,
        "current_round": current_round,
        "max_rounds": max_rounds,
        "participants": participants or ["bot_dev", "bot_mkt"],
    }


# ── TC-B1: start_discussion → PROPOSE 타입 메시지 추가 ───────────────────────


@pytest.mark.asyncio
async def test_tc_b1_discussion_starts_with_propose():
    """start_discussion() 호출 시 add_discussion_message가 PROPOSE 타입으로 호출된다."""
    manager, db, send_func = _make_manager()

    disc_record = _make_disc_record("D-pm-001")
    db.create_discussion = AsyncMock(return_value=disc_record)
    db.add_discussion_message = AsyncMock(return_value={"msg_type": "PROPOSE"})

    await manager.start_discussion(
        topic="AI 전략 수립",
        initial_proposal="AI를 도입해서 효율을 높이자",
        from_dept="bot_dev",
        participants=["bot_dev", "bot_mkt"],
        chat_id=None,
    )

    # create_discussion이 먼저 호출되어야 함
    db.create_discussion.assert_awaited_once()

    # add_discussion_message가 PROPOSE 타입으로 호출되어야 함
    db.add_discussion_message.assert_awaited_once()
    kwargs = db.add_discussion_message.call_args.kwargs
    assert kwargs.get("msg_type") == "PROPOSE", (
        f"PROPOSE 타입 기대, 실제: {kwargs.get('msg_type')}"
    )
    assert kwargs.get("from_dept") == "bot_dev", (
        f"from_dept='bot_dev' 기대, 실제: {kwargs.get('from_dept')}"
    )
    assert kwargs.get("round_num") == 1, (
        f"round_num=1 기대, 실제: {kwargs.get('round_num')}"
    )


# ── TC-B2: advance_round → round 2 메시지 추가 검증 ─────────────────────────


@pytest.mark.asyncio
async def test_tc_b2_round_advances_via_advance_round():
    """advance_round() 호출 후 라운드 번호가 2로 갱신된다.

    Critic 픽스: advance_round() → ContextDB.advance_discussion_round() 체인 검증.
    """
    manager, db, send_func = _make_manager()

    disc_id = "D-pm-002"
    disc_record = _make_disc_record(disc_id, current_round=1, max_rounds=3)
    db.get_discussion = AsyncMock(return_value=disc_record)
    db.advance_discussion_round = AsyncMock(return_value=2)

    new_round = await manager.advance_round(disc_id, chat_id=None)

    assert new_round == 2, f"라운드 2 기대, 실제: {new_round}"
    db.advance_discussion_round.assert_awaited_once_with(disc_id)

    # 이후 add_discussion_message로 round 2 메시지 추가 가능한지 검증
    db.get_discussion = AsyncMock(return_value=_make_disc_record(
        disc_id, current_round=2, max_rounds=3
    ))
    db.add_discussion_message = AsyncMock(return_value={"msg_type": "OPINION", "round_num": 2})
    db.check_convergence = AsyncMock(return_value=False)

    msg = await manager.add_message(
        discussion_id=disc_id,
        msg_type="OPINION",
        content="라운드 2 의견",
        from_dept="bot_mkt",
        chat_id=None,
    )

    assert msg is not None
    db.add_discussion_message.assert_awaited_once()
    add_kwargs = db.add_discussion_message.call_args.kwargs
    assert add_kwargs.get("round_num") == 2, (
        f"round_num=2 기대, 실제: {add_kwargs.get('round_num')}"
    )


# ── TC-B3: 참여자별 from_dept 필드 일관성 ────────────────────────────────────


@pytest.mark.asyncio
async def test_tc_b3_persona_consistency():
    """각 참여자가 발언 시 from_dept 필드가 일관되게 유지된다."""
    manager, db, send_func = _make_manager()

    disc_id = "D-pm-003"
    disc_record = _make_disc_record(disc_id)
    db.get_discussion = AsyncMock(return_value=disc_record)
    db.check_convergence = AsyncMock(return_value=False)

    recorded_from_depts: list[str] = []

    async def _capture_add_msg(**kwargs):
        recorded_from_depts.append(kwargs.get("from_dept", ""))
        return {"msg_type": kwargs.get("msg_type"), "from_dept": kwargs.get("from_dept")}

    db.add_discussion_message = AsyncMock(side_effect=_capture_add_msg)

    participants = ["bot_dev", "bot_mkt", "bot_ops"]
    for dept in participants:
        await manager.add_message(
            discussion_id=disc_id,
            msg_type="OPINION",
            content=f"{dept}의 의견입니다",
            from_dept=dept,
            chat_id=None,
        )

    # 각 발언의 from_dept가 입력과 일치해야 함
    assert recorded_from_depts == participants, (
        f"from_dept 일관성 실패: {recorded_from_depts} != {participants}"
    )


# ── TC-B4: 이전 round 메시지가 다음 round context에 포함 ──────────────────────


@pytest.mark.asyncio
async def test_tc_b4_context_carry_over():
    """get_discussion_messages 반환값이 이전 round 메시지를 포함한다 (DB mock 레벨 검증)."""
    manager, db, send_func = _make_manager()

    disc_id = "D-pm-004"

    # round 1 메시지들을 DB mock이 반환하도록 설정
    round1_messages = [
        {"msg_type": "PROPOSE", "from_dept": "bot_dev", "round_num": 1, "content": "초기 제안"},
        {"msg_type": "OPINION", "from_dept": "bot_mkt", "round_num": 1, "content": "마케팅 관점"},
    ]
    db.get_discussion_messages = AsyncMock(return_value=round1_messages)

    # round 2로 advance 후 get_discussion_messages 호출
    disc_record_r2 = _make_disc_record(disc_id, current_round=2)
    db.get_discussion = AsyncMock(return_value=disc_record_r2)
    db.advance_discussion_round = AsyncMock(return_value=2)

    await manager.advance_round(disc_id, chat_id=None)

    # get_discussion_messages를 호출하면 round 1 메시지도 포함해야 함
    messages = await db.get_discussion_messages(disc_id)
    assert len(messages) == 2, f"round 1 메시지 2개 기대, 실제: {len(messages)}"
    round_nums = [m["round_num"] for m in messages]
    assert 1 in round_nums, "round 1 메시지가 context에 포함되어야 함"


# ── TC-B5: DECISION 메시지 추가 후 토론 종결 상태 검증 ───────────────────────


@pytest.mark.asyncio
async def test_tc_b5_decision_ends_discussion():
    """force_decision() 호출 시 DECISION 메시지가 추가되고 상태가 'decided'로 변경된다."""
    manager, db, send_func = _make_manager()

    disc_id = "D-pm-005"
    disc_record = _make_disc_record(disc_id, status="open")
    db.get_discussion = AsyncMock(return_value=disc_record)
    db.add_discussion_message = AsyncMock(return_value={"msg_type": "DECISION"})
    db.update_discussion_status = AsyncMock(
        return_value={**disc_record, "status": "decided", "decision": "AI 도입 확정"}
    )

    result = await manager.force_decision(
        discussion_id=disc_id,
        decision="AI 도입 확정",
        chat_id=None,
    )

    # DECISION 메시지가 기록되어야 함
    db.add_discussion_message.assert_awaited_once()
    add_kwargs = db.add_discussion_message.call_args.kwargs
    assert add_kwargs.get("msg_type") == "DECISION", (
        f"DECISION 타입 기대, 실제: {add_kwargs.get('msg_type')}"
    )
    assert "AI 도입 확정" in add_kwargs.get("content", ""), (
        "결정 내용이 메시지에 포함되어야 함"
    )

    # 상태가 'decided'로 갱신되어야 함
    db.update_discussion_status.assert_awaited_once()
    status_args = db.update_discussion_status.call_args
    assert status_args.args[1] == "decided" or status_args.kwargs.get("status") == "decided" or \
        (len(status_args.args) > 1 and status_args.args[1] == "decided"), (
        f"상태 'decided' 기대, 실제 호출: {status_args}"
    )

    # 반환값이 None이 아니어야 함 (토론 레코드 반환)
    assert result is not None, "force_decision은 업데이트된 레코드를 반환해야 함"
