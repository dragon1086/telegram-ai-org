"""bot_dispatcher.py — 봇 메시지 라우팅·디스패치 모듈 (Phase 1c 분리).

telegram_relay.py의 메시지 라우팅 및 핸들러 디스패치 로직을 추출한 모듈.
- 수신 메시지 → 명령어 / 협업 요청 / PM 작업 / 일반 메시지 라우팅
- 협업 요청 처리 (_handle_collab_request)
- 명령어 처리 (_handle_command)
- 코드 수정 승인/거절 처리 (_handle_approve_code_fix, _handle_reject_code_fix)
- 메시지 타입 판별 유틸리티

Feature Flag: ENABLE_REFACTORED_DISPATCHER (기본값: True)
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol, runtime_checkable

ENABLE_REFACTORED_DISPATCHER = os.environ.get("ENABLE_REFACTORED_DISPATCHER", "1") == "1"

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


@runtime_checkable
class DispatchRelayProtocol(Protocol):
    """TelegramRelay 에서 디스패치에 필요한 최소 인터페이스.

    TelegramRelay가 이 프로토콜을 암묵적으로 만족하므로 별도 상속 불필요.
    """

    org_id: str
    allowed_chat_id: int
    _is_dept_org: bool
    _is_pm_org: bool

    async def _handle_command(self, text: str, update: object, context: object) -> None: ...
    async def _handle_collab_request(self, text: str, update: object, context: object) -> None: ...
    async def _handle_approve_code_fix(self, approval_id: str, update: object, ctx: object) -> None: ...
    async def _handle_reject_code_fix(self, approval_id: str, update: object, ctx: object) -> None: ...


async def dispatch_command(
    relay: DispatchRelayProtocol,
    text: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/ 명령어 처리 위임.

    TelegramRelay._handle_command()의 위임 진입점.
    on_message()에서 text.startswith('/') 분기를 대체한다.

    Args:
        relay: TelegramRelay 인스턴스 (DispatchRelayProtocol 충족)
        text: 명령어 텍스트 (/ 로 시작)
        update: Telegram Update 객체
        context: Telegram ContextTypes
    """
    await relay._handle_command(text, update, context)


async def dispatch_collab_request(
    relay: DispatchRelayProtocol,
    text: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """협업 요청 메시지 처리 위임.

    TelegramRelay._handle_collab_request()의 위임 진입점.
    """
    await relay._handle_collab_request(text, update, context)


async def dispatch_bot_message(
    relay: DispatchRelayProtocol,
    text: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """봇 발신 메시지 라우팅 디스패치.

    on_message()의 봇 메시지 분기를 담당.
    협업 요청만 여기서 처리하고, PM 전용 처리(PM_TASK, 토론, PM_DONE)는
    pm_message_handler.handle_bot_message()로 위임한다.

    Args:
        relay: TelegramRelay 인스턴스
        text: 메시지 텍스트
        update: Telegram Update 객체
        context: Telegram ContextTypes

    Returns:
        True — 처리 완료 (호출자는 return해야 함)
        False — 처리하지 않음
    """
    from core.collab_request import is_collab_request

    sender = update.effective_message.from_user  # type: ignore[union-attr]
    if not (sender and sender.is_bot):
        return False

    if is_collab_request(text):
        await relay._handle_collab_request(text, update, context)
        return True

    return False


async def dispatch_approve_code_fix(
    relay: DispatchRelayProtocol,
    approval_id: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """코드 자동 수정 승인 처리 위임.

    TelegramRelay._handle_approve_code_fix()의 위임 진입점.
    """
    await relay._handle_approve_code_fix(approval_id, update, context)


async def dispatch_reject_code_fix(
    relay: DispatchRelayProtocol,
    approval_id: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """코드 자동 수정 거절 처리 위임.

    TelegramRelay._handle_reject_code_fix()의 위임 진입점.
    """
    await relay._handle_reject_code_fix(approval_id, update, context)


def classify_message_type(text: str, *, is_bot_sender: bool) -> str:
    """메시지 타입 분류 유틸리티.

    TelegramRelay.on_message()의 분기 조건을 명시적으로 표현.
    새로운 라우팅 로직 작성 시 이 함수를 참조한다.

    Args:
        text: 메시지 텍스트
        is_bot_sender: 발신자가 봇인지 여부

    Returns:
        메시지 타입 문자열:
        - "command": / 명령어
        - "collab_request": 봇 발신 협업 요청
        - "pm_task": 봇 발신 PM_TASK 지시
        - "discussion": 봇 발신 토론 메시지
        - "pm_done": 봇 발신 태스크 완료/실패 이벤트
        - "user_message": 일반 사용자 메시지
        - "bot_other": 처리 대상 아닌 봇 메시지
    """
    import re

    from core.collab_request import is_collab_request
    from core.discussion_parser import is_discussion_message

    if text.startswith("/"):
        return "command"

    if is_bot_sender:
        if is_collab_request(text):
            return "collab_request"
        if "[PM_TASK:" in text:
            return "pm_task"
        if is_discussion_message(text):
            return "discussion"
        if re.search(r"태스크\s+T-[A-Za-z0-9_]+-\d+\s+(완료|실패)", text):
            return "pm_done"
        return "bot_other"

    return "user_message"


def get_handler_registry() -> dict[str, str]:
    """현재 활성화된 핸들러 레지스트리 반환.

    디버깅 및 모니터링용 유틸리티. 각 메시지 타입에 매핑된
    핸들러 모듈 경로를 반환한다.
    """
    from core.pm_message_handler import ENABLE_REFACTORED_PM_HANDLER

    return {
        "command": "core.telegram_relay.TelegramRelay._handle_command",
        "collab_request": (
            "core.bot_dispatcher.dispatch_collab_request"
            if ENABLE_REFACTORED_DISPATCHER
            else "core.telegram_relay.TelegramRelay._handle_collab_request"
        ),
        "pm_task": (
            "core.pm_message_handler.handle_bot_message"
            if ENABLE_REFACTORED_PM_HANDLER
            else "core.telegram_relay.TelegramRelay._handle_pm_task"
        ),
        "discussion": (
            "core.pm_message_handler.handle_bot_message"
            if ENABLE_REFACTORED_PM_HANDLER
            else "core.telegram_relay.TelegramRelay._handle_discussion_message"
        ),
        "pm_done": (
            "core.pm_message_handler.handle_bot_message"
            if ENABLE_REFACTORED_PM_HANDLER
            else "core.telegram_relay.TelegramRelay._handle_pm_done_event"
        ),
        "user_message": "core.telegram_relay.TelegramRelay.on_message",
    }
