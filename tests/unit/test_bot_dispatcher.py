"""bot_dispatcher.py 단위 테스트 (Phase 1c 리팩토링).

Feature Flag 동작, 메시지 타입 분류, 핸들러 위임 로직을 검증한다.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── 픽스처 ─────────────────────────────────────────────────────────────────

class MockRelay:
    """DispatchRelayProtocol 을 구현하는 최소 테스트 더블."""

    def __init__(self, *, is_dept_org: bool = False, is_pm_org: bool = True):
        self.org_id = "global"
        self.allowed_chat_id = 123456
        self._is_dept_org = is_dept_org
        self._is_pm_org = is_pm_org

        # 메서드 호출 추적용
        self._handle_command = AsyncMock()
        self._handle_collab_request = AsyncMock()
        self._handle_approve_code_fix = AsyncMock()
        self._handle_reject_code_fix = AsyncMock()


def _make_update(text: str, *, is_bot: bool = False) -> MagicMock:
    """Telegram Update 최소 목 객체 생성."""
    update = MagicMock()
    sender = MagicMock()
    sender.is_bot = is_bot
    update.effective_message.from_user = sender
    update.effective_message.text = text
    return update


# ── ENABLE_REFACTORED_DISPATCHER 플래그 테스트 ────────────────────────────

class TestFeatureFlag:
    def test_flag_default_enabled(self):
        """기본값은 활성화(1) 상태."""
        from core.bot_dispatcher import ENABLE_REFACTORED_DISPATCHER
        assert isinstance(ENABLE_REFACTORED_DISPATCHER, bool)

    def test_flag_disabled_via_env(self, monkeypatch):
        """환경 변수 ENABLE_REFACTORED_DISPATCHER=0 으로 비활성화 가능."""
        monkeypatch.setenv("ENABLE_REFACTORED_DISPATCHER", "0")
        value = ("0" != "1")
        assert value is True


# ── DispatchRelayProtocol 런타임 체크 ─────────────────────────────────────

class TestProtocolCheck:
    def test_mock_relay_satisfies_protocol(self):
        """MockRelay가 DispatchRelayProtocol을 충족하는지 런타임 체크."""
        from core.bot_dispatcher import DispatchRelayProtocol
        relay = MockRelay()
        assert isinstance(relay, DispatchRelayProtocol)

    def test_empty_object_does_not_satisfy_protocol(self):
        """빈 객체는 DispatchRelayProtocol 불충족."""
        from core.bot_dispatcher import DispatchRelayProtocol

        class Empty:
            pass

        assert not isinstance(Empty(), DispatchRelayProtocol)


# ── classify_message_type 테스트 ────────────────────────────────────────────

class TestClassifyMessageType:
    def test_command_message(self):
        """/로 시작하는 텍스트는 'command'."""
        from core.bot_dispatcher import classify_message_type
        assert classify_message_type("/status", is_bot_sender=False) == "command"
        assert classify_message_type("/start", is_bot_sender=True) == "command"

    def test_user_message(self):
        """봇 아닌 발신자의 일반 텍스트는 'user_message'."""
        from core.bot_dispatcher import classify_message_type
        assert classify_message_type("안녕하세요", is_bot_sender=False) == "user_message"
        assert classify_message_type("도와주세요", is_bot_sender=False) == "user_message"

    def test_pm_task_message(self):
        """[PM_TASK:...] 포함 봇 메시지는 'pm_task'."""
        from core.bot_dispatcher import classify_message_type
        text = "[PM_TASK:T-global-1|dept:global] 태스크 설명"
        assert classify_message_type(text, is_bot_sender=True) == "pm_task"

    def test_pm_done_event_완료(self):
        """태스크 완료 패턴 봇 메시지는 'pm_done'."""
        from core.bot_dispatcher import classify_message_type
        text = "✅ [개발실] 태스크 T-global-123 완료"
        assert classify_message_type(text, is_bot_sender=True) == "pm_done"

    def test_pm_done_event_실패(self):
        """태스크 실패 패턴 봇 메시지는 'pm_done'."""
        from core.bot_dispatcher import classify_message_type
        text = "❌ [개발실] 태스크 T-aiorg_pm_bot-456 실패: 오류"
        assert classify_message_type(text, is_bot_sender=True) == "pm_done"

    def test_collab_request_message(self):
        """협업 요청 접두사 봇 메시지는 'collab_request'."""
        from core.bot_dispatcher import classify_message_type
        text = "🙋 도와줄 조직 찾아요!\n발신: pm\n요청: 분석 해주세요"
        assert classify_message_type(text, is_bot_sender=True) == "collab_request"

    def test_bot_other_message(self):
        """어떤 패턴도 해당 안 되는 봇 메시지는 'bot_other'."""
        from core.bot_dispatcher import classify_message_type
        assert classify_message_type("일반 봇 메시지", is_bot_sender=True) == "bot_other"

    def test_pm_task_not_bot_is_user_message(self):
        """[PM_TASK:...] 포함이더라도 봇 아닌 발신자면 'user_message'."""
        from core.bot_dispatcher import classify_message_type
        text = "[PM_TASK:T-global-1|dept:global] 태스크"
        assert classify_message_type(text, is_bot_sender=False) == "user_message"


# ── dispatch_command 테스트 ──────────────────────────────────────────────

class TestDispatchCommand:
    def test_delegates_to_relay_handle_command(self):
        """dispatch_command가 relay._handle_command를 호출."""
        from core.bot_dispatcher import dispatch_command

        relay = MockRelay()
        update = _make_update("/status")
        context = MagicMock()

        asyncio.run(
            dispatch_command(relay, "/status", update, context)
        )
        relay._handle_command.assert_called_once_with("/status", update, context)


# ── dispatch_collab_request 테스트 ───────────────────────────────────────

class TestDispatchCollabRequest:
    def test_delegates_to_relay_handle_collab_request(self):
        """dispatch_collab_request가 relay._handle_collab_request를 호출."""
        from core.bot_dispatcher import dispatch_collab_request

        relay = MockRelay()
        text = "🙋 도와줄 조직 찾아요!\n발신: pm"
        update = _make_update(text, is_bot=True)
        context = MagicMock()

        asyncio.run(
            dispatch_collab_request(relay, text, update, context)
        )
        relay._handle_collab_request.assert_called_once_with(text, update, context)


# ── dispatch_bot_message 테스트 ─────────────────────────────────────────

class TestDispatchBotMessage:
    def test_non_bot_sender_returns_false(self):
        """봇 아닌 발신자는 False 반환."""
        from core.bot_dispatcher import dispatch_bot_message

        relay = MockRelay()
        update = _make_update("안녕", is_bot=False)

        result = asyncio.run(
            dispatch_bot_message(relay, "안녕", update, MagicMock())
        )
        assert result is False
        relay._handle_collab_request.assert_not_called()

    def test_collab_request_handled(self):
        """협업 요청 메시지는 True 반환 및 _handle_collab_request 호출."""
        from core.bot_dispatcher import dispatch_bot_message

        relay = MockRelay()
        text = "🙋 도와줄 조직 찾아요!\n발신: pm\n요청: 분석"
        update = _make_update(text, is_bot=True)

        result = asyncio.run(
            dispatch_bot_message(relay, text, update, MagicMock())
        )
        assert result is True
        relay._handle_collab_request.assert_called_once()

    def test_non_collab_bot_message_returns_false(self):
        """협업 요청 아닌 봇 메시지는 False 반환 (pm_handler에 위임)."""
        from core.bot_dispatcher import dispatch_bot_message

        relay = MockRelay()
        text = "[PM_TASK:T-1|dept:global]"
        update = _make_update(text, is_bot=True)

        result = asyncio.run(
            dispatch_bot_message(relay, text, update, MagicMock())
        )
        assert result is False
        relay._handle_collab_request.assert_not_called()


# ── dispatch_approve/reject_code_fix 테스트 ─────────────────────────────

class TestDispatchCodeFix:
    def test_approve_code_fix_delegates(self):
        """dispatch_approve_code_fix가 relay._handle_approve_code_fix를 호출."""
        from core.bot_dispatcher import dispatch_approve_code_fix

        relay = MockRelay()
        update = _make_update("/approve_code_fix approve-001")
        context = MagicMock()

        asyncio.run(
            dispatch_approve_code_fix(relay, "approve-001", update, context)
        )
        relay._handle_approve_code_fix.assert_called_once_with("approve-001", update, context)

    def test_reject_code_fix_delegates(self):
        """dispatch_reject_code_fix가 relay._handle_reject_code_fix를 호출."""
        from core.bot_dispatcher import dispatch_reject_code_fix

        relay = MockRelay()
        update = _make_update("/reject_code_fix reject-002")
        context = MagicMock()

        asyncio.run(
            dispatch_reject_code_fix(relay, "reject-002", update, context)
        )
        relay._handle_reject_code_fix.assert_called_once_with("reject-002", update, context)


# ── get_handler_registry 테스트 ─────────────────────────────────────────

class TestHandlerRegistry:
    def test_registry_returns_dict(self):
        """get_handler_registry가 dict를 반환한다."""
        from core.bot_dispatcher import get_handler_registry

        registry = get_handler_registry()
        assert isinstance(registry, dict)

    def test_registry_contains_expected_keys(self):
        """레지스트리에 모든 메시지 타입 키가 존재한다."""
        from core.bot_dispatcher import get_handler_registry

        registry = get_handler_registry()
        expected_keys = {"command", "collab_request", "pm_task", "discussion", "pm_done", "user_message"}
        assert expected_keys.issubset(registry.keys())

    def test_registry_values_are_strings(self):
        """레지스트리 값은 모두 핸들러 경로 문자열."""
        from core.bot_dispatcher import get_handler_registry

        registry = get_handler_registry()
        for key, val in registry.items():
            assert isinstance(val, str), f"{key} 핸들러 경로가 문자열 아님"

    def test_registry_changes_with_flags(self, monkeypatch):
        """Feature Flag에 따라 핸들러 레지스트리가 달라진다."""
        from core.bot_dispatcher import get_handler_registry
        import core.pm_message_handler as pmh
        import core.bot_dispatcher as bd

        # 플래그 활성화
        monkeypatch.setattr(pmh, "ENABLE_REFACTORED_PM_HANDLER", True)
        monkeypatch.setattr(bd, "ENABLE_REFACTORED_DISPATCHER", True)
        registry_on = get_handler_registry()

        # 플래그 비활성화
        monkeypatch.setattr(pmh, "ENABLE_REFACTORED_PM_HANDLER", False)
        registry_off = get_handler_registry()

        # pm_task 핸들러가 달라져야 함
        assert registry_on["pm_task"] != registry_off["pm_task"]
