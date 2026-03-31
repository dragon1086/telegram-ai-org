"""pm_message_handler.py 순환참조 방지 규칙 단위 테스트 (RETRO-15/RETRO-17).

CIRC-001 ~ CIRC-004 규칙을 PM 핸들러 컨텍스트에서 검증한다.
"""
from __future__ import annotations

import pytest

from core.pm_message_handler import (
    _MAX_ORCHESTRATION_DEPTH,
    _MAX_ROUTING_HOPS,
    check_pm_circular_ref,
)


class TestCIRC001SenderEqualsTarget:
    """CIRC-001: PM 컨텍스트 — sender_id == target_bot_id 금지."""

    def test_raises_when_pm_sender_equals_target(self):
        with pytest.raises(ValueError, match=r"\[CIRC-001\]"):
            check_pm_circular_ref(sender_id="pm_bot", target_bot_id="pm_bot")

    def test_passes_when_sender_differs(self):
        check_pm_circular_ref(sender_id="pm_bot", target_bot_id="worker_bot")

    def test_passes_with_none_ids(self):
        check_pm_circular_ref(sender_id=None, target_bot_id=None)


class TestCIRC002RoutingHops:
    """CIRC-002: PM 컨텍스트 — 라우팅 홉 최대 3회 제한."""

    def test_raises_when_hops_exceeded(self):
        with pytest.raises(ValueError, match=r"\[CIRC-002\]"):
            check_pm_circular_ref(routing_hops=_MAX_ROUTING_HOPS + 1)

    def test_passes_at_boundary(self):
        check_pm_circular_ref(routing_hops=_MAX_ROUTING_HOPS)

    def test_passes_zero_hops(self):
        check_pm_circular_ref(routing_hops=0)


class TestCIRC003ReplyLoop:
    """CIRC-003: PM 컨텍스트 — reply_to_message 순환 금지."""

    def test_raises_on_self_reply(self):
        with pytest.raises(ValueError, match=r"\[CIRC-003\]"):
            check_pm_circular_ref(reply_sender_id="pm_bot_id", current_bot_id="pm_bot_id")

    def test_passes_when_different_bots(self):
        check_pm_circular_ref(reply_sender_id="worker_a", current_bot_id="pm_bot")


class TestCIRC004OrchestrationDepth:
    """CIRC-004: PM 컨텍스트 — 오케스트레이션 깊이 최대 10 제한."""

    def test_raises_when_depth_exceeded(self):
        with pytest.raises(ValueError, match=r"\[CIRC-004\]"):
            check_pm_circular_ref(orchestration_depth=_MAX_ORCHESTRATION_DEPTH + 1)

    def test_passes_at_max(self):
        check_pm_circular_ref(orchestration_depth=_MAX_ORCHESTRATION_DEPTH)

    def test_passes_zero_depth(self):
        check_pm_circular_ref(orchestration_depth=0)


class TestAllRulesPassPM:
    """PM 핸들러: 모든 규칙 통과 정상 케이스."""

    def test_normal_pm_dispatch_passes_all_rules(self):
        check_pm_circular_ref(
            sender_id="worker_bot",
            target_bot_id="pm_bot",
            routing_hops=2,
            orchestration_depth=5,
            reply_sender_id="worker_bot",
            current_bot_id="pm_bot",
        )
