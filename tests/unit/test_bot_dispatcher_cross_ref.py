"""bot_dispatcher.py 순환참조 방지 규칙 단위 테스트 (RETRO-15/RETRO-17).

CIRC-001 ~ CIRC-004 규칙을 디스패처 컨텍스트에서 검증한다.
"""
from __future__ import annotations

import pytest

from core.bot_dispatcher import (
    _MAX_ORCHESTRATION_DEPTH,
    _MAX_ROUTING_HOPS,
    check_dispatch_circular_ref,
)


class TestCIRC001SenderEqualsTarget:
    """CIRC-001: 디스패처 — sender_id == target_bot_id 금지."""

    def test_raises_on_same_ids(self):
        with pytest.raises(ValueError, match=r"\[CIRC-001\]"):
            check_dispatch_circular_ref(sender_id=7, target_bot_id=7)

    def test_raises_on_same_string_ids(self):
        with pytest.raises(ValueError, match=r"\[CIRC-001\]"):
            check_dispatch_circular_ref(sender_id="relay_bot", target_bot_id="relay_bot")

    def test_passes_on_different_ids(self):
        check_dispatch_circular_ref(sender_id=1, target_bot_id=2)

    def test_passes_with_none(self):
        check_dispatch_circular_ref(sender_id=None, target_bot_id=None)


class TestCIRC002RoutingHops:
    """CIRC-002: 디스패처 — 라우팅 홉 최대 3회 제한."""

    def test_raises_when_exceeded(self):
        with pytest.raises(ValueError, match=r"\[CIRC-002\]"):
            check_dispatch_circular_ref(routing_hops=_MAX_ROUTING_HOPS + 1)

    def test_passes_at_max_boundary(self):
        check_dispatch_circular_ref(routing_hops=_MAX_ROUTING_HOPS)

    def test_passes_zero(self):
        check_dispatch_circular_ref(routing_hops=0)


class TestCIRC003ReplyLoop:
    """CIRC-003: 디스패처 — reply_to_message 순환 금지."""

    def test_raises_when_reply_is_self(self):
        with pytest.raises(ValueError, match=r"\[CIRC-003\]"):
            check_dispatch_circular_ref(reply_sender_id=55, current_bot_id=55)

    def test_passes_on_different_bots(self):
        check_dispatch_circular_ref(reply_sender_id=10, current_bot_id=20)

    def test_passes_with_none_values(self):
        check_dispatch_circular_ref(reply_sender_id=None, current_bot_id=55)


class TestCIRC004OrchestrationDepth:
    """CIRC-004: 디스패처 — 오케스트레이션 깊이 최대 10 제한."""

    def test_raises_when_depth_exceeded(self):
        with pytest.raises(ValueError, match=r"\[CIRC-004\]"):
            check_dispatch_circular_ref(orchestration_depth=_MAX_ORCHESTRATION_DEPTH + 1)

    def test_passes_at_max(self):
        check_dispatch_circular_ref(orchestration_depth=_MAX_ORCHESTRATION_DEPTH)

    def test_passes_zero_depth(self):
        check_dispatch_circular_ref(orchestration_depth=0)


class TestAllRulesPassDispatcher:
    """디스패처: 모든 규칙 통과 정상 케이스."""

    def test_normal_dispatch_passes_all_rules(self):
        check_dispatch_circular_ref(
            sender_id="user_123",
            target_bot_id="dev_bot",
            routing_hops=1,
            orchestration_depth=2,
            reply_sender_id="user_123",
            current_bot_id="dev_bot",
        )
