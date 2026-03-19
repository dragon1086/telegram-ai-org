"""MessageEnvelope E2E 테스트 — 자연어 통신 + 메타데이터 분리 검증."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.message_envelope import MessageEnvelope


def test_tc_e1_to_display_hides_metadata():
    """TC-E1: to_display()는 content만 반환, 메타데이터 미포함."""
    env = MessageEnvelope.wrap(
        content="알겠어, 마케팅 분석 시작할게요.",
        sender_bot="dev_bot",
        intent="TASK_ACCEPT",
        task_id="T-001",
        priority="high",
    )
    display = env.to_display()
    assert display == "알겠어, 마케팅 분석 시작할게요."
    assert "TASK_ACCEPT" not in display
    assert "dev_bot" not in display
    assert "T-001" not in display
    assert "priority" not in display


def test_tc_e2_to_wire_includes_all_metadata():
    """TC-E2: to_wire()는 전체 메타데이터 포함."""
    env = MessageEnvelope.wrap(
        content="분석 완료했어요.",
        sender_bot="analyst_bot",
        intent="TASK_DONE",
        task_id="T-002",
        reply_to=12345,
    )
    wire = env.to_wire()
    assert wire["content"] == "분석 완료했어요."
    assert wire["sender_bot"] == "analyst_bot"
    assert wire["intent"] == "TASK_DONE"
    assert wire["task_id"] == "T-002"
    assert wire["reply_to"] == 12345


def test_tc_e3_roundtrip_from_wire():
    """TC-E3: to_wire() → from_wire() 왕복 후 동일한 값."""
    original = MessageEnvelope.wrap(
        content="회의 시작합시다.",
        sender_bot="pm_bot",
        intent="MEETING_START",
        task_id="T-003",
    )
    wire = original.to_wire()
    restored = MessageEnvelope.from_wire(wire)
    assert restored.content == original.content
    assert restored.intent == original.intent
    assert restored.sender_bot == original.sender_bot
    assert restored.task_id == original.task_id


def test_tc_e4_extract_legacy_tags_parses_collab_request():
    """TC-E4: 기존 [TYPE:value] 태그 파싱 성공."""
    raw = "도움 요청드립니다 [COLLAB_REQUEST:bot_a] 확인 부탁해요"
    result = MessageEnvelope.extract_legacy_tags(raw)
    assert result["type"] == "COLLAB_REQUEST"
    assert result["value"] == "bot_a"


def test_tc_e5_extract_legacy_tags_graceful_fallback():
    """TC-E5: 태그 없는 메시지에 graceful fallback (빈 dict)."""
    raw = "안녕하세요! 오늘 회의 어떠셨나요?"
    result = MessageEnvelope.extract_legacy_tags(raw)
    assert result == {}
