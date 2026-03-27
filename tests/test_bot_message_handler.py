"""bot_message_handler.py 스모크 테스트 — Phase 1b 리팩토링 검증."""
from __future__ import annotations

import asyncio
from dataclasses import fields
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.bot_message_handler import (
    ATTACHMENT_GROUP_DEBOUNCE_SEC,
    ENABLE_REFACTORED_HANDLER,
    PM_DONE_PATTERN,
    AttachmentGroupState,
    MessageClassifier,
    download_attachment,
)


# ─── 상수 테스트 ──────────────────────────────────────────────────────────────
class TestConstants:
    def test_debounce_sec(self):
        assert ATTACHMENT_GROUP_DEBOUNCE_SEC == 1.2

    def test_enable_flag_is_false_by_default(self):
        assert ENABLE_REFACTORED_HANDLER is False

    def test_pm_done_pattern_matches_complete(self):
        assert PM_DONE_PATTERN.search("태스크 T-aiorg_pm_bot-123 완료")

    def test_pm_done_pattern_matches_fail(self):
        assert PM_DONE_PATTERN.search("태스크 T-aiorg_pm_bot-456 실패")

    def test_pm_done_pattern_no_match(self):
        assert not PM_DONE_PATTERN.search("일반 메시지입니다")


# ─── AttachmentGroupState 테스트 ──────────────────────────────────────────────
class TestAttachmentGroupState:
    def test_default_fields(self):
        state = AttachmentGroupState()
        assert state.items == []
        assert state.caption == ""
        assert state.message is None
        assert state.task is None

    def test_is_dataclass(self):
        field_names = {f.name for f in fields(AttachmentGroupState)}
        assert {"items", "caption", "message", "task"} == field_names


# ─── MessageClassifier 테스트 ─────────────────────────────────────────────────
class TestMessageClassifier:
    def test_is_bot_sender_true(self):
        sender = MagicMock(is_bot=True)
        assert MessageClassifier.is_bot_sender(sender) is True

    def test_is_bot_sender_false(self):
        sender = MagicMock(is_bot=False)
        assert MessageClassifier.is_bot_sender(sender) is False

    def test_is_bot_sender_none(self):
        assert MessageClassifier.is_bot_sender(None) is False

    def test_is_command_true(self):
        assert MessageClassifier.is_command("/start") is True

    def test_is_command_false(self):
        assert MessageClassifier.is_command("hello") is False

    def test_is_command_empty(self):
        assert MessageClassifier.is_command("") is False

    def test_is_pm_done_event_complete(self):
        assert MessageClassifier.is_pm_done_event("태스크 T-aiorg_pm_bot-123 완료") is True

    def test_is_pm_done_event_fail(self):
        assert MessageClassifier.is_pm_done_event("태스크 T-foo-999 실패") is True

    def test_is_pm_done_event_no_match(self):
        assert MessageClassifier.is_pm_done_event("아무 메시지") is False

    def test_is_old_message_old(self):
        assert MessageClassifier.is_old_message(100.0, 300.0, grace_sec=120.0) is True

    def test_is_old_message_within_grace(self):
        # msg_ts=200, start=300, grace=120 → 200 >= 300-120=180 → not old
        assert MessageClassifier.is_old_message(200.0, 300.0, grace_sec=120.0) is False

    def test_is_old_message_zero_ts(self):
        assert MessageClassifier.is_old_message(0.0, 300.0) is False

    def test_is_startup_recovery_true(self):
        # msg_ts < start_time
        assert MessageClassifier.is_startup_recovery_message(290.0, 300.0) is True

    def test_is_startup_recovery_false(self):
        assert MessageClassifier.is_startup_recovery_message(310.0, 300.0) is False

    def test_extract_text(self):
        msg = MagicMock(text="hello")
        assert MessageClassifier.extract_text(msg) == "hello"

    def test_extract_text_none(self):
        msg = MagicMock(text=None)
        assert MessageClassifier.extract_text(msg) == ""


# ─── download_attachment 테스트 ───────────────────────────────────────────────
class TestDownloadAttachment:
    def _make_context(self, tg_file_mock):
        ctx = MagicMock()
        ctx.bot.get_file = AsyncMock(return_value=tg_file_mock)
        return ctx

    def _make_tg_file(self):
        f = MagicMock()
        f.download_to_drive = AsyncMock()
        return f

    @pytest.mark.asyncio
    async def test_document(self, tmp_path):
        tg_file = self._make_tg_file()
        ctx = self._make_context(tg_file)
        msg = MagicMock(
            document=MagicMock(file_id="fid", file_name="test.pdf", mime_type="application/pdf"),
            photo=None,
            video=None,
            audio=None,
            voice=None,
            caption=None,
            message_id=1,
        )
        result = await download_attachment(msg, ctx, tmp_path)
        assert result is not None
        assert result.kind == "document"
        assert result.original_filename == "test.pdf"

    @pytest.mark.asyncio
    async def test_photo(self, tmp_path):
        tg_file = self._make_tg_file()
        ctx = self._make_context(tg_file)
        photo_obj = MagicMock(file_id="pid")
        msg = MagicMock(
            document=None,
            photo=[photo_obj],
            video=None,
            audio=None,
            voice=None,
            caption=None,
            message_id=2,
        )
        result = await download_attachment(msg, ctx, tmp_path)
        assert result is not None
        assert result.kind == "photo"
        assert result.mime_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_unsupported_returns_none(self, tmp_path):
        ctx = self._make_context(MagicMock())
        msg = MagicMock(
            document=None,
            photo=None,
            video=None,
            audio=None,
            voice=None,
        )
        result = await download_attachment(msg, ctx, tmp_path)
        assert result is None

    @pytest.mark.asyncio
    async def test_voice(self, tmp_path):
        tg_file = self._make_tg_file()
        ctx = self._make_context(tg_file)
        msg = MagicMock(
            document=None,
            photo=None,
            video=None,
            audio=None,
            voice=MagicMock(file_id="vid"),
            caption=None,
            message_id=3,
        )
        result = await download_attachment(msg, ctx, tmp_path)
        assert result is not None
        assert result.kind == "voice"
        assert result.mime_type == "audio/ogg"
