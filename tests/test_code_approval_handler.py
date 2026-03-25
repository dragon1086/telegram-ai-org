"""TelegramRelay 코드 수정 승인/거절 핸들러 단위 테스트.

_handle_approve_code_fix / _handle_reject_code_fix 핸들러가
CodeImprovementApprovalStore 상태를 올바르게 전환하고
SelfCodeImprover를 백그라운드 태스크로 실행하는지 검증한다.

NOTE: telegram_relay.py의 두 핸들러는 함수 내부에서 lazy import를 사용한다.
      실제 store 인스턴스를 tmp_path 기반으로 생성하고,
      CodeImprovementApprovalStore 클래스 자체를 패치하여 동일 인스턴스가 반환되도록 한다.
"""
from __future__ import annotations

import asyncio
import dataclasses
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.code_improvement_approval_store import CodeImprovementApprovalStore
from core.improvement_bus import ImprovementSignal, SignalKind

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

PATCH_STORE = "core.code_improvement_approval_store.CodeImprovementApprovalStore"


def _make_relay():
    """TelegramRelay 인스턴스를 최소 의존성으로 생성."""
    from core.telegram_relay import TelegramRelay

    return TelegramRelay(
        token="fake-token",
        allowed_chat_id=99,
        session_manager=MagicMock(),
        memory_manager=MagicMock(),
        org_id="aiorg_engineering_bot",
        context_db=None,
    )


def _make_update():
    update = MagicMock()
    update.effective_chat.id = 99
    update.message.reply_text = AsyncMock()
    return update


def _make_context():
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def _make_code_signal() -> ImprovementSignal:
    return ImprovementSignal(
        kind=SignalKind.CODE_SMELL,
        priority=9,
        target="code:nl_classifier.py",
        evidence={"size_kb": 160},
        suggested_action="nl_classifier.py 분리 권장.",
    )


def _enqueue(store: CodeImprovementApprovalStore) -> str:
    return store.enqueue(dataclasses.asdict(_make_code_signal()))


async def _await_background_tasks() -> None:
    """현재 테스트 태스크를 제외한 백그라운드 태스크만 수거한다."""
    await asyncio.sleep(0.05)
    current = asyncio.current_task()
    tasks = [
        task for task in asyncio.all_tasks()
        if task is not current and not task.done()
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# approve 핸들러 — approval_id 없을 때 pending 목록 반환
# ---------------------------------------------------------------------------

class TestApproveHandlerNoPendingId:
    @pytest.mark.asyncio
    async def test_no_pending_sends_empty_message(self, tmp_path):
        """pending 항목 없이 /approve_code_fix 호출 시 '없습니다' 안내."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")

        with patch(PATCH_STORE, return_value=store):
            await relay._handle_approve_code_fix("", update, ctx)

        call_text = update.message.reply_text.await_args.args[0]
        assert "없습니다" in call_text

    @pytest.mark.asyncio
    async def test_with_pending_lists_items(self, tmp_path):
        """pending 항목이 있으면 목록과 approve 커맨드를 응답한다."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        approval_id = _enqueue(store)

        with patch(PATCH_STORE, return_value=store):
            await relay._handle_approve_code_fix("", update, ctx)

        call_text = update.message.reply_text.await_args.args[0]
        assert approval_id in call_text
        assert "approve_code_fix" in call_text


# ---------------------------------------------------------------------------
# approve 핸들러 — 잘못된 approval_id
# ---------------------------------------------------------------------------

class TestApproveHandlerInvalidId:
    @pytest.mark.asyncio
    async def test_nonexistent_id_replies_error(self, tmp_path):
        """존재하지 않는 approval_id 승인 시 오류 메시지 반환."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")

        with patch(PATCH_STORE, return_value=store):
            await relay._handle_approve_code_fix("nonexistent_id", update, ctx)

        call_text = update.message.reply_text.await_args.args[0]
        assert "찾을 수 없거나" in call_text


# ---------------------------------------------------------------------------
# approve 핸들러 — 성공 케이스 (SelfCodeImprover 목킹)
# ---------------------------------------------------------------------------

class TestApproveHandlerSuccess:
    @pytest.mark.asyncio
    async def test_approve_sends_ack_immediately(self, tmp_path):
        """승인 즉시 '승인 완료' 응답이 전송된다."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        approval_id = _enqueue(store)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.branch = "fix/auto-2026-03-24-nl_classifier"
        mock_result.commit_hash = "abc1234567"
        mock_result.attempts = 1

        with (
            patch(PATCH_STORE, return_value=store),
            patch("core.self_code_improver.SelfCodeImprover.fix", new=AsyncMock(return_value=mock_result)),
        ):
            await relay._handle_approve_code_fix(approval_id, update, ctx)
            await _await_background_tasks()

        ack_text = update.message.reply_text.await_args.args[0]
        assert "승인 완료" in ack_text

    @pytest.mark.asyncio
    async def test_approve_transitions_store_status(self, tmp_path):
        """store.approve() 호출 후 상태가 approved로 전환된다."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        approval_id = _enqueue(store)

        # fix()가 무한 대기하지 않도록 즉시 반환하는 mock 사용
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.attempts = 1
        mock_result.error_message = "mocked"

        with (
            patch(PATCH_STORE, return_value=store),
            patch("core.self_code_improver.SelfCodeImprover.fix", new=AsyncMock(return_value=mock_result)),
        ):
            await relay._handle_approve_code_fix(approval_id, update, ctx)
            await _await_background_tasks()

        # 최소한 approved로 전환됐는지 확인 (executed는 fix 성공 후)
        final_status = store.get_status(approval_id)
        assert final_status in ("approved", "executed"), f"예상치 못한 상태: {final_status}"

    @pytest.mark.asyncio
    async def test_approve_sends_result_on_success(self, tmp_path):
        """SelfCodeImprover 성공 시 Telegram으로 결과 메시지가 전송된다."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        approval_id = _enqueue(store)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.branch = "fix/auto-2026-03-24-nl_classifier"
        mock_result.commit_hash = "deadbeef1234abcd"
        mock_result.attempts = 1

        with (
            patch(PATCH_STORE, return_value=store),
            patch("core.self_code_improver.SelfCodeImprover.fix", new=AsyncMock(return_value=mock_result)),
        ):
            await relay._handle_approve_code_fix(approval_id, update, ctx)
            await _await_background_tasks()

        # 백그라운드 결과 보고 — send_message 호출 확인
        assert ctx.bot.send_message.called
        result_msg = ctx.bot.send_message.await_args.kwargs.get(
            "text", ctx.bot.send_message.await_args.args[1] if len(ctx.bot.send_message.await_args.args) > 1 else ""
        )
        assert "완료" in result_msg or "수정" in result_msg

    @pytest.mark.asyncio
    async def test_approve_marks_executed_after_success(self, tmp_path):
        """fix() 성공 시 mark_executed() 호출로 상태가 executed로 전환된다."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        approval_id = _enqueue(store)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.branch = "fix/auto-test"
        mock_result.commit_hash = "cafebabe5678abcd"
        mock_result.attempts = 1

        with (
            patch(PATCH_STORE, return_value=store),
            patch("core.self_code_improver.SelfCodeImprover.fix", new=AsyncMock(return_value=mock_result)),
        ):
            await relay._handle_approve_code_fix(approval_id, update, ctx)
            await _await_background_tasks()

        assert store.get_status(approval_id) == "executed"


# ---------------------------------------------------------------------------
# reject 핸들러
# ---------------------------------------------------------------------------

class TestRejectHandler:
    @pytest.mark.asyncio
    async def test_reject_no_id_sends_usage(self, tmp_path):
        """approval_id 없이 /reject_code_fix 호출 시 사용법 안내."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")

        with patch(PATCH_STORE, return_value=store):
            await relay._handle_reject_code_fix("", update, ctx)

        call_text = update.message.reply_text.await_args.args[0]
        assert "사용법" in call_text

    @pytest.mark.asyncio
    async def test_reject_nonexistent_id_replies_error(self, tmp_path):
        """존재하지 않는 approval_id 거절 시 오류 메시지 반환."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")

        with patch(PATCH_STORE, return_value=store):
            await relay._handle_reject_code_fix("badid", update, ctx)

        call_text = update.message.reply_text.await_args.args[0]
        assert "찾을 수 없거나" in call_text

    @pytest.mark.asyncio
    async def test_reject_valid_id_transitions_status(self, tmp_path):
        """유효한 approval_id 거절 시 상태가 rejected로 전환된다."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        approval_id = _enqueue(store)

        with patch(PATCH_STORE, return_value=store):
            await relay._handle_reject_code_fix(approval_id, update, ctx)

        assert store.get_status(approval_id) == "rejected"

    @pytest.mark.asyncio
    async def test_reject_sends_cancel_confirmation(self, tmp_path):
        """거절 시 '거절됨' 확인 메시지가 approval_id와 함께 전송된다."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        approval_id = _enqueue(store)

        with patch(PATCH_STORE, return_value=store):
            await relay._handle_reject_code_fix(approval_id, update, ctx)

        call_text = update.message.reply_text.await_args.args[0]
        assert "거절" in call_text
        assert approval_id in call_text

    @pytest.mark.asyncio
    async def test_reject_prevents_approved_listing(self, tmp_path):
        """거절된 항목은 list_approved()에 포함되지 않는다."""
        relay = _make_relay()
        update = _make_update()
        ctx = _make_context()
        store = CodeImprovementApprovalStore(path=tmp_path / "approval.json")
        approval_id = _enqueue(store)

        with patch(PATCH_STORE, return_value=store):
            await relay._handle_reject_code_fix(approval_id, update, ctx)

        assert store.list_approved() == []
