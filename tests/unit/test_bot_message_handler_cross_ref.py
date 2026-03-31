"""bot_message_handler.py 순환참조 방지 규칙 단위 테스트 (RETRO-15/RETRO-17).

CIRC-001 ~ CIRC-004 규칙을 검증한다.
"""
from __future__ import annotations

import pytest

from core.bot_message_handler import (
    MAX_ORCHESTRATION_DEPTH,
    MAX_ROUTING_HOPS,
    check_circular_ref,
)


class TestCIRC001SenderEqualsTarget:
    """CIRC-001: sender_id == target_bot_id 금지."""

    def test_raises_when_sender_equals_target(self):
        with pytest.raises(ValueError, match=r"\[CIRC-001\]"):
            check_circular_ref(sender_id=42, target_bot_id=42)

    def test_raises_when_sender_equals_target_str(self):
        with pytest.raises(ValueError, match=r"\[CIRC-001\]"):
            check_circular_ref(sender_id="bot_123", target_bot_id="bot_123")

    def test_passes_when_sender_differs_from_target(self):
        check_circular_ref(sender_id=1, target_bot_id=2)  # no exception

    def test_passes_when_either_is_none(self):
        check_circular_ref(sender_id=None, target_bot_id=42)
        check_circular_ref(sender_id=42, target_bot_id=None)
        check_circular_ref(sender_id=None, target_bot_id=None)


class TestCIRC002RoutingHops:
    """CIRC-002: 라우팅 홉 최대 3회 제한."""

    def test_raises_when_hops_exceeded(self):
        with pytest.raises(ValueError, match=r"\[CIRC-002\]"):
            check_circular_ref(routing_hops=MAX_ROUTING_HOPS + 1)

    def test_passes_at_max_hops(self):
        check_circular_ref(routing_hops=MAX_ROUTING_HOPS)  # no exception

    def test_passes_below_max_hops(self):
        check_circular_ref(routing_hops=0)
        check_circular_ref(routing_hops=1)
        check_circular_ref(routing_hops=2)


class TestCIRC003ReplyLoop:
    """CIRC-003: reply_to_message 발신자가 현재 봇과 같으면 금지."""

    def test_raises_when_reply_sender_equals_current_bot(self):
        with pytest.raises(ValueError, match=r"\[CIRC-003\]"):
            check_circular_ref(reply_sender_id=99, current_bot_id=99)

    def test_passes_when_reply_sender_differs(self):
        check_circular_ref(reply_sender_id=1, current_bot_id=2)

    def test_passes_when_either_is_none(self):
        check_circular_ref(reply_sender_id=None, current_bot_id=99)
        check_circular_ref(reply_sender_id=99, current_bot_id=None)


class TestCIRC004OrchestrationDepth:
    """CIRC-004: 오케스트레이션 깊이 최대 10 제한."""

    def test_raises_when_depth_exceeded(self):
        with pytest.raises(ValueError, match=r"\[CIRC-004\]"):
            check_circular_ref(orchestration_depth=MAX_ORCHESTRATION_DEPTH + 1)

    def test_passes_at_max_depth(self):
        check_circular_ref(orchestration_depth=MAX_ORCHESTRATION_DEPTH)

    def test_passes_below_max_depth(self):
        check_circular_ref(orchestration_depth=0)
        check_circular_ref(orchestration_depth=5)


class TestAllRulesPass:
    """모든 규칙이 통과되는 정상 케이스."""

    def test_normal_message_passes_all_rules(self):
        check_circular_ref(
            sender_id=100,
            target_bot_id=200,
            routing_hops=1,
            orchestration_depth=3,
            reply_sender_id=100,
            current_bot_id=200,
        )
