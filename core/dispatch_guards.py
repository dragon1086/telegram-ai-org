"""dispatch_guards.py — 디스패치 공통 순환참조 방지 유틸리티.

bot_dispatcher.py / bot_message_handler.py / pm_message_handler.py 의
중복 check_*_circular_ref 로직을 단일 구현으로 통합.

각 모듈은 이 함수를 import하여 사용하고 자신의 이름으로 re-export한다.
"""
from __future__ import annotations

# ─── 순환참조 방지 상수 (RETRO-17 설계값) ────────────────────────────────────
MAX_ORCHESTRATION_DEPTH: int = 10
"""오케스트레이션 최대 깊이 제한 (CIRC-004)."""

MAX_ROUTING_HOPS: int = 3
"""라우팅 최대 홉 수 제한 (CIRC-002)."""


def check_circular_ref_impl(
    sender_id: object = None,
    target_bot_id: object = None,
    routing_hops: int | None = None,
    orchestration_depth: int | None = None,
    reply_sender_id: object = None,
    current_bot_id: object = None,
    *,
    context_label: str = "디스패처",
) -> None:
    """순환참조 방지 4규칙 검증 공통 구현 (RETRO-17 CIRC-001 ~ CIRC-004).

    Args:
        sender_id: 메시지 발신자 ID
        target_bot_id: 라우팅 대상 봇 ID
        routing_hops: 현재까지 라우팅 홉 수
        orchestration_depth: 현재 오케스트레이션 깊이
        reply_sender_id: reply_to_message 의 발신자 ID
        current_bot_id: 현재 처리 중인 봇 ID
        context_label: 에러 메시지에 포함할 컨텍스트 이름

    Raises:
        ValueError: 순환참조 규칙 위반 시 [CIRC-00N] 마커 포함 메시지
    """
    # CIRC-001: sender_id == target_bot_id 금지
    if sender_id is not None and target_bot_id is not None and sender_id == target_bot_id:
        raise ValueError(
            f"[CIRC-001] sender_id({sender_id!r}) == target_bot_id({target_bot_id!r}): "
            f"{context_label} 자기 참조가 감지되었습니다."
        )

    # CIRC-002: 라우팅 홉 초과 금지
    if routing_hops is not None and routing_hops > MAX_ROUTING_HOPS:
        raise ValueError(
            f"[CIRC-002] routing_hops({routing_hops}) > MAX_ROUTING_HOPS({MAX_ROUTING_HOPS}): "
            f"{context_label} 라우팅 홉 한도를 초과했습니다."
        )

    # CIRC-003: reply 발신자 == 현재 봇 금지
    if reply_sender_id is not None and current_bot_id is not None and reply_sender_id == current_bot_id:
        raise ValueError(
            f"[CIRC-003] reply_sender_id({reply_sender_id!r}) == current_bot_id({current_bot_id!r}): "
            f"{context_label} reply_to_message 순환 참조가 감지되었습니다."
        )

    # CIRC-004: 오케스트레이션 깊이 초과 금지
    if orchestration_depth is not None and orchestration_depth > MAX_ORCHESTRATION_DEPTH:
        raise ValueError(
            f"[CIRC-004] orchestration_depth({orchestration_depth}) > MAX_ORCHESTRATION_DEPTH({MAX_ORCHESTRATION_DEPTH}): "
            f"{context_label} 오케스트레이션 깊이 한도를 초과했습니다."
        )


__all__ = [
    "MAX_ORCHESTRATION_DEPTH",
    "MAX_ROUTING_HOPS",
    "check_circular_ref_impl",
]
