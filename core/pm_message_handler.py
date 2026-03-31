"""pm_message_handler.py — PM 전용 메시지 처리 모듈 (Phase 1c 분리).

telegram_relay.py의 PM 특화 메시지 처리 로직을 추출한 모듈.
- PM 배정 태스크 실행 (_execute_pm_task / _execute_polled_task)
- PM 완료 이벤트 처리 (_handle_pm_done_event)
- PM 채팅 응답 (_reply_with_pm_chat)
- 토론 메시지 처리 (_handle_discussion_message)
- PM 봇 메시지 디스패치 (handle_bot_message)

Feature Flag: ENABLE_REFACTORED_PM_HANDLER (기본값: True)
"""
from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Protocol, runtime_checkable

ENABLE_REFACTORED_PM_HANDLER = os.environ.get("ENABLE_REFACTORED_PM_HANDLER", "1") == "1"

# ─── 순환참조 방지 상수 (RETRO-17 설계값) ────────────────────────────────────
_MAX_ORCHESTRATION_DEPTH: int = 10
"""오케스트레이션 최대 깊이 제한 (CIRC-004)."""

_MAX_ROUTING_HOPS: int = 3
"""라우팅 최대 홉 수 제한 (CIRC-002)."""


def check_pm_circular_ref(
    sender_id: object = None,
    target_bot_id: object = None,
    routing_hops: int | None = None,
    orchestration_depth: int | None = None,
    reply_sender_id: object = None,
    current_bot_id: object = None,
) -> None:
    """PM 컨텍스트 순환참조 방지 4규칙 검증 (RETRO-17 CIRC-001 ~ CIRC-004).

    Args:
        sender_id: 메시지 발신자 ID
        target_bot_id: 라우팅 대상 봇 ID
        routing_hops: 현재까지 라우팅 홉 수
        orchestration_depth: 현재 오케스트레이션 깊이
        reply_sender_id: reply_to_message 의 발신자 ID
        current_bot_id: 현재 처리 중인 봇 ID

    Raises:
        ValueError: 순환참조 규칙 위반 시 [CIRC-00N] 마커 포함 메시지
    """
    # CIRC-001: sender_id == target_bot_id 금지
    if sender_id is not None and target_bot_id is not None and sender_id == target_bot_id:
        raise ValueError(
            f"[CIRC-001] sender_id({sender_id!r}) == target_bot_id({target_bot_id!r}): "
            "PM 자기 참조가 감지되었습니다."
        )

    # CIRC-002: 라우팅 홉 초과 금지
    if routing_hops is not None and routing_hops > _MAX_ROUTING_HOPS:
        raise ValueError(
            f"[CIRC-002] routing_hops({routing_hops}) > _MAX_ROUTING_HOPS({_MAX_ROUTING_HOPS}): "
            "PM 라우팅 홉 한도를 초과했습니다."
        )

    # CIRC-003: reply 발신자 == 현재 봇 금지
    if reply_sender_id is not None and current_bot_id is not None and reply_sender_id == current_bot_id:
        raise ValueError(
            f"[CIRC-003] reply_sender_id({reply_sender_id!r}) == current_bot_id({current_bot_id!r}): "
            "PM reply_to_message 순환 참조가 감지되었습니다."
        )

    # CIRC-004: 오케스트레이션 깊이 초과 금지
    if orchestration_depth is not None and orchestration_depth > _MAX_ORCHESTRATION_DEPTH:
        raise ValueError(
            f"[CIRC-004] orchestration_depth({orchestration_depth}) > _MAX_ORCHESTRATION_DEPTH({_MAX_ORCHESTRATION_DEPTH}): "
            "PM 오케스트레이션 깊이 한도를 초과했습니다."
        )


if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


@runtime_checkable
class PMRelayProtocol(Protocol):
    """TelegramRelay 에서 PM 메시지 처리에 필요한 최소 인터페이스.

    TelegramRelay가 이 프로토콜을 암묵적으로 만족하므로 별도 상속 불필요.
    """

    org_id: str
    allowed_chat_id: int
    context_db: object | None
    _is_dept_org: bool
    _is_pm_org: bool
    _pm_orchestrator: object | None
    _discussion_manager: object | None
    _synthesizing: set
    bus: object | None

    async def _execute_pm_task(self, task_info: dict) -> None: ...
    async def _handle_pm_done_event(self, text: str) -> None: ...
    async def _reply_with_pm_chat(self, update: object, text: str, replied_context: str) -> None: ...
    async def _handle_discussion_message(self, text: str, update: object, context: object) -> None: ...


async def handle_bot_message(
    relay: PMRelayProtocol,
    text: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """봇 발신 메시지에 대한 PM 전용 처리 로직.

    TelegramRelay.on_message() 내 봇 메시지 분기를 위임받는 진입점.

    Args:
        relay: TelegramRelay 인스턴스 (PMRelayProtocol 충족)
        text: 메시지 텍스트
        update: Telegram Update 객체
        context: Telegram ContextTypes

    Returns:
        True — 이 함수에서 처리 완료 (호출자는 return해야 함)
        False — 처리하지 않음 (호출자가 계속 진행)
    """
    from core.collab_request import is_collab_request
    from core.discussion_parser import is_discussion_message

    sender = update.effective_message.from_user  # type: ignore[union-attr]
    if not (sender and sender.is_bot):
        return False

    if is_collab_request(text):
        # 협업 요청은 bot_dispatcher가 처리 — 여기서는 스킵
        return False

    if relay._is_dept_org and "[PM_TASK:" in text:
        await relay._handle_pm_task(text, update, context)  # type: ignore[attr-defined]
        return True

    if relay._discussion_manager and is_discussion_message(text):
        await relay._handle_discussion_message(text, update, context)
        return True

    if relay._pm_orchestrator is not None and re.search(
        r"태스크\s+T-[A-Za-z0-9_]+-\d+\s+(완료|실패)", text
    ):
        await relay._handle_pm_done_event(text)
        return True

    return False


async def execute_polled_task(
    relay: PMRelayProtocol,
    task_info: dict,
) -> None:
    """TaskPoller 콜백 — ContextDB에서 감지된 태스크 실행.

    TelegramRelay._execute_polled_task()의 위임 진입점.
    """
    await relay._execute_pm_task(task_info)


async def handle_pm_done_event(
    relay: PMRelayProtocol,
    text: str,
) -> None:
    """워커봇 완료/실패 메시지 수신 시 즉시 합성 트리거.

    TelegramRelay._handle_pm_done_event()의 위임 진입점.
    """
    await relay._handle_pm_done_event(text)


async def handle_discussion_message(
    relay: PMRelayProtocol,
    text: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """토론 태그 메시지 처리 — DiscussionManager에 위임.

    TelegramRelay._handle_discussion_message()의 위임 진입점.
    """
    await relay._handle_discussion_message(text, update, context)


async def reply_with_pm_chat(
    relay: PMRelayProtocol,
    update: Update,
    text: str,
    replied_context: str = "",
) -> None:
    """가벼운 질문/상태 확인 PM 직접 응답.

    TelegramRelay._reply_with_pm_chat()의 위임 진입점.
    """
    await relay._reply_with_pm_chat(update, text, replied_context)
