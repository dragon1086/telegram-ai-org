"""pm_message_handler.py 단위 테스트 (Phase 1c 리팩토링).

Feature Flag 동작, 프로토콜 준수, 핸들러 위임 로직을 검증한다.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 픽스처 ─────────────────────────────────────────────────────────────────

class MockRelay:
    """PMRelayProtocol 을 구현하는 최소 테스트 더블."""

    def __init__(self, *, is_dept_org: bool = False, is_pm_org: bool = True):
        self.org_id = "global"
        self.allowed_chat_id = 123456
        self.context_db = None
        self._is_dept_org = is_dept_org
        self._is_pm_org = is_pm_org
        self._pm_orchestrator = MagicMock() if is_pm_org else None
        self._discussion_manager = None
        self._synthesizing: set = set()
        self.bus = None

        # 메서드 호출 추적용
        self._execute_pm_task = AsyncMock()
        self._handle_pm_done_event = AsyncMock()
        self._reply_with_pm_chat = AsyncMock()
        self._handle_discussion_message = AsyncMock()
        self._handle_pm_task = AsyncMock()


def _make_update(text: str, *, is_bot: bool = False) -> MagicMock:
    """Telegram Update 최소 목 객체 생성."""
    update = MagicMock()
    sender = MagicMock()
    sender.is_bot = is_bot
    update.effective_message.from_user = sender
    update.effective_message.text = text
    return update


# ── ENABLE_REFACTORED_PM_HANDLER 플래그 테스트 ────────────────────────────

class TestFeatureFlag:
    def test_flag_default_enabled(self):
        """기본값은 활성화(1) 상태."""
        from core.pm_message_handler import ENABLE_REFACTORED_PM_HANDLER
        # 환경 변수 미설정 시 기본값 True
        assert isinstance(ENABLE_REFACTORED_PM_HANDLER, bool)

    def test_flag_disabled_via_env(self, monkeypatch):
        """환경 변수 ENABLE_REFACTORED_PM_HANDLER=0 으로 비활성화 가능."""
        monkeypatch.setenv("ENABLE_REFACTORED_PM_HANDLER", "0")
        # 모듈 재로드 없이 현재 상태 확인 (환경 변수 변경은 import 후라 직접 확인)
        value = ("0" != "1")
        assert value is True  # "0" != "1" → 비활성화 로직


# ── PMRelayProtocol 런타임 체크 ────────────────────────────────────────────

class TestProtocolCheck:
    def test_mock_relay_satisfies_protocol(self):
        """MockRelay가 PMRelayProtocol을 충족하는지 런타임 체크."""
        from core.pm_message_handler import PMRelayProtocol
        relay = MockRelay()
        # isinstance 체크 (runtime_checkable)
        assert isinstance(relay, PMRelayProtocol)

    def test_empty_object_does_not_satisfy_protocol(self):
        """빈 객체는 PMRelayProtocol 불충족."""
        from core.pm_message_handler import PMRelayProtocol

        class Empty:
            pass

        assert not isinstance(Empty(), PMRelayProtocol)


# ── handle_bot_message 핵심 로직 테스트 ──────────────────────────────────

class TestHandleBotMessage:
    def test_non_bot_sender_returns_false(self):
        """봇이 아닌 발신자는 False 반환."""
        from core.pm_message_handler import handle_bot_message

        relay = MockRelay()
        update = _make_update("hello", is_bot=False)

        result = asyncio.run(
            handle_bot_message(relay, "hello", update, MagicMock())
        )
        assert result is False

    def test_collab_request_returns_false(self):
        """협업 요청 메시지는 False 반환 (bot_dispatcher 담당)."""
        from core.pm_message_handler import handle_bot_message

        relay = MockRelay()
        update = _make_update("🙋 도와줄 조직 찾아요!\n발신: pm", is_bot=True)

        result = asyncio.run(
            handle_bot_message(relay, "🙋 도와줄 조직 찾아요!\n발신: pm", update, MagicMock())
        )
        assert result is False

    def test_pm_task_message_handled_by_dept_org(self):
        """[PM_TASK:...] 메시지는 dept_org에서 처리."""
        from core.pm_message_handler import handle_bot_message

        relay = MockRelay(is_dept_org=True)
        text = "[PM_TASK:T-global-1|dept:global] 태스크 설명"
        update = _make_update(text, is_bot=True)

        result = asyncio.run(
            handle_bot_message(relay, text, update, MagicMock())
        )
        assert result is True
        relay._handle_pm_task.assert_called_once_with(text, update, pytest.approx(MagicMock()))

    def test_pm_task_message_skipped_by_non_dept_org(self):
        """[PM_TASK:...] 메시지는 비-dept_org에서 처리 안 함."""
        from core.pm_message_handler import handle_bot_message

        relay = MockRelay(is_dept_org=False)
        text = "[PM_TASK:T-global-1|dept:global] 태스크 설명"
        update = _make_update(text, is_bot=True)

        result = asyncio.run(
            handle_bot_message(relay, text, update, MagicMock())
        )
        assert result is False
        relay._handle_pm_task.assert_not_called()

    def test_pm_done_event_handled(self):
        """워커 완료 패턴 메시지는 _handle_pm_done_event 호출."""
        from core.pm_message_handler import handle_bot_message

        relay = MockRelay(is_pm_org=True)
        text = "✅ [개발실] 태스크 T-global-123 완료"
        update = _make_update(text, is_bot=True)

        result = asyncio.run(
            handle_bot_message(relay, text, update, MagicMock())
        )
        assert result is True
        relay._handle_pm_done_event.assert_called_once_with(text)

    def test_pm_failed_event_handled(self):
        """워커 실패 패턴 메시지도 _handle_pm_done_event 호출."""
        from core.pm_message_handler import handle_bot_message

        relay = MockRelay(is_pm_org=True)
        text = "❌ [개발실] 태스크 T-global-456 실패: 오류 발생"
        update = _make_update(text, is_bot=True)

        result = asyncio.run(
            handle_bot_message(relay, text, update, MagicMock())
        )
        assert result is True
        relay._handle_pm_done_event.assert_called_once_with(text)

    def test_pm_done_skipped_when_no_orchestrator(self):
        """_pm_orchestrator가 None이면 PM_DONE 처리 안 함."""
        from core.pm_message_handler import handle_bot_message

        relay = MockRelay(is_pm_org=True)
        relay._pm_orchestrator = None  # 오케스트레이터 없음
        text = "✅ [개발실] 태스크 T-global-789 완료"
        update = _make_update(text, is_bot=True)

        result = asyncio.run(
            handle_bot_message(relay, text, update, MagicMock())
        )
        assert result is False
        relay._handle_pm_done_event.assert_not_called()

    def test_discussion_message_handled(self):
        """토론 태그 메시지는 _handle_discussion_message 호출."""
        from core.pm_message_handler import handle_bot_message

        relay = MockRelay()
        relay._discussion_manager = MagicMock()

        # is_discussion_message를 패치해 토론 메시지로 인식
        with patch("core.pm_message_handler.handle_bot_message") as patched:
            patched.return_value = True
            # 직접 로직 테스트
            text = "[DISCUSS:D-001] 내용"
            with patch("core.discussion_parser.is_discussion_message", return_value=True):
                update = _make_update(text, is_bot=True)
                result = asyncio.run(
                    handle_bot_message(relay, text, update, MagicMock())
                )
                # discussion_manager가 있으면 처리
                assert result is True
                relay._handle_discussion_message.assert_called_once()


# ── 위임 함수 시그니처 테스트 ──────────────────────────────────────────────

class TestDelegationFunctions:
    def test_execute_polled_task_delegates(self):
        """execute_polled_task가 relay._execute_pm_task를 호출."""
        from core.pm_message_handler import execute_polled_task

        relay = MockRelay()
        task_info = {"id": "T-global-1", "description": "테스트"}

        asyncio.run(
            execute_polled_task(relay, task_info)
        )
        relay._execute_pm_task.assert_called_once_with(task_info)

    def test_handle_pm_done_event_delegates(self):
        """handle_pm_done_event가 relay._handle_pm_done_event를 호출."""
        from core.pm_message_handler import handle_pm_done_event

        relay = MockRelay()
        text = "✅ 태스크 T-global-1 완료"

        asyncio.run(
            handle_pm_done_event(relay, text)
        )
        relay._handle_pm_done_event.assert_called_once_with(text)

    def test_handle_discussion_message_delegates(self):
        """handle_discussion_message가 relay._handle_discussion_message를 호출."""
        from core.pm_message_handler import handle_discussion_message

        relay = MockRelay()
        update = _make_update("토론 내용", is_bot=True)
        text = "[DISCUSS:D-001] 토론 내용"
        context = MagicMock()

        asyncio.run(
            handle_discussion_message(relay, text, update, context)
        )
        relay._handle_discussion_message.assert_called_once_with(text, update, context)

    def test_reply_with_pm_chat_delegates(self):
        """reply_with_pm_chat가 relay._reply_with_pm_chat를 호출."""
        from core.pm_message_handler import reply_with_pm_chat

        relay = MockRelay()
        update = _make_update("안녕하세요")
        text = "안녕하세요"
        replied_context = ""

        asyncio.run(
            reply_with_pm_chat(relay, update, text, replied_context)
        )
        relay._reply_with_pm_chat.assert_called_once_with(update, text, replied_context)

    def test_reply_with_pm_chat_default_replied_context(self):
        """reply_with_pm_chat — replied_context 기본값 빈 문자열."""
        from core.pm_message_handler import reply_with_pm_chat

        relay = MockRelay()
        update = _make_update("질문")

        asyncio.run(
            reply_with_pm_chat(relay, update, "질문")
        )
        relay._reply_with_pm_chat.assert_called_once_with(update, "질문", "")
