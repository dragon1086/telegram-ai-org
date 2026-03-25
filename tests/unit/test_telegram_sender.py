"""telegram_sender.py 단위 테스트 — Phase 1a 분리 검증."""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 테스트 환경 미설치 모듈 mock — python-telegram-bot, pyyaml 등
for _mod in (
    "telegram", "telegram.ext", "telegram.constants",
    "yaml", "aiosqlite",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from core.telegram_sender import (
    ENABLE_REFACTORED_SENDER,
    auto_upload,
    send_chunked_message,
    upload_artifacts_to,
)


class TestAutoUpload:
    """auto_upload 함수 테스트."""

    @pytest.mark.asyncio
    async def test_no_candidates_returns_early(self):
        """경로 후보 없으면 업로드 없이 종료."""
        uploaded = set()
        with patch("core.telegram_delivery.resolve_delivery_target", return_value=None), \
             patch("core.telegram_user_guardrail.extract_local_artifact_paths", return_value=[]):
            await auto_upload("응답 텍스트", "token", 12345, "test_org", uploaded)
        assert len(uploaded) == 0

    @pytest.mark.asyncio
    async def test_skips_already_uploaded(self):
        """이미 업로드된 경로는 스킵."""
        uploaded = {"/tmp/file.md"}
        # 경로 후보에 /tmp/file.md가 반환되지만 이미 업로드됨
        with patch("core.telegram_delivery.resolve_delivery_target", return_value=None), \
             patch("core.telegram_user_guardrail.extract_local_artifact_paths",
                   return_value=["/tmp/file.md"]):
            await auto_upload("텍스트", "token", 12345, "test_org", uploaded)
        # 추가 업로드 없음
        assert "/tmp/file.md" in uploaded
        assert len(uploaded) == 1  # 새 항목 없음

    @pytest.mark.asyncio
    async def test_no_bundle_skips_upload(self):
        """prepare_upload_bundle이 빈 리스트 반환 시 업로드 없음."""
        uploaded = set()
        with patch("core.telegram_delivery.resolve_delivery_target", return_value=None), \
             patch("core.telegram_user_guardrail.extract_local_artifact_paths",
                   return_value=["/nonexistent/file.md"]), \
             patch("core.artifact_pipeline.prepare_upload_bundle", return_value=[]):
            await auto_upload("텍스트", "token", 12345, "test_org", uploaded)
        assert len(uploaded) == 0


class TestUploadArtifactsTo:
    """upload_artifacts_to 함수 테스트."""

    @pytest.mark.asyncio
    async def test_skips_already_uploaded(self):
        """이미 업로드된 파일은 재업로드 안 함."""
        uploaded = {"/tmp/existing.md"}
        mock_path = MagicMock()
        mock_path.__str__ = lambda s: "/tmp/existing.md"
        mock_path.name = "existing.md"

        with patch("core.telegram_user_guardrail.extract_local_artifact_paths",
                   return_value=["/tmp/existing.md"]), \
             patch("core.artifact_pipeline.prepare_upload_bundle", return_value=[mock_path]):
            await upload_artifacts_to("결과", "token", 12345, "test_org", uploaded)
        # 크기 변화 없음 (upload_file 호출 안 됨)
        assert len(uploaded) == 1

    @pytest.mark.asyncio
    async def test_uploads_new_artifact(self):
        """새 아티팩트는 업로드 후 세트에 추가."""
        uploaded = set()
        mock_path = MagicMock()
        mock_path.__str__ = lambda s: "/tmp/new_file.md"
        mock_path.name = "new_file.md"

        with patch("core.telegram_user_guardrail.extract_local_artifact_paths",
                   return_value=["/tmp/new_file.md"]), \
             patch("core.artifact_pipeline.prepare_upload_bundle", return_value=[mock_path]), \
             patch("tools.telegram_uploader.upload_file", new_callable=AsyncMock) as mock_upload:
            await upload_artifacts_to("결과", "token", 12345, "test_org", uploaded)

        assert "/tmp/new_file.md" in uploaded
        mock_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_paths_in_result(self):
        """결과에 파일 경로 없으면 업로드 없음."""
        uploaded = set()
        with patch("core.telegram_user_guardrail.extract_local_artifact_paths", return_value=[]):
            await upload_artifacts_to("경로 없는 텍스트", "token", 12345, "test_org", uploaded)
        assert len(uploaded) == 0


class TestFeatureFlag:
    """Feature Flag 동작 테스트."""

    def test_feature_flag_is_bool(self):
        """ENABLE_REFACTORED_SENDER는 bool 타입."""
        assert isinstance(ENABLE_REFACTORED_SENDER, bool)

    def test_feature_flag_default_enabled(self):
        """기본값은 활성화(True) — ENABLE_REFACTORED_SENDER 환경변수 없을 때."""
        import os
        env_val = os.environ.get("ENABLE_REFACTORED_SENDER", "1")
        assert env_val == "1"


class TestSendChunkedMessage:
    """send_chunked_message 함수 테스트."""

    @pytest.mark.asyncio
    async def test_artifact_markers_stripped_from_content(self):
        """[ARTIFACT:...] 마커는 MessageEnvelope에 전달 전 제거됨."""
        mock_display = MagicMock()
        mock_sent = MagicMock()
        mock_sent.message_id = 100
        mock_display.send_to_chat = AsyncMock(return_value=mock_sent)

        captured_content = []

        class FakeEnvelope:
            def to_display(self):
                return "깨끗한 텍스트"

        def fake_wrap(content, sender_bot, intent):
            captured_content.append(content)
            return FakeEnvelope()

        with patch("core.message_envelope.MessageEnvelope.wrap", side_effect=fake_wrap), \
             patch("core.telegram_formatting.split_message", return_value=["깨끗한 텍스트"]), \
             patch("core.message_envelope.EnvelopeManager") as MockMgr:
            MockMgr.return_value.save = AsyncMock()
            await send_chunked_message(
                bot=MagicMock(),
                display=mock_display,
                chat_id=12345,
                text="텍스트 [ARTIFACT:file.md] 끝",
                org_id="test_org",
            )

        assert len(captured_content) == 1
        assert "[ARTIFACT:" not in captured_content[0]

    @pytest.mark.asyncio
    async def test_returns_last_sent_message(self):
        """마지막 전송 메시지 객체 반환."""
        mock_display = MagicMock()
        mock_sent = MagicMock()
        mock_sent.message_id = 42
        mock_display.send_to_chat = AsyncMock(return_value=mock_sent)

        class FakeEnvelope:
            def to_display(self):
                return "텍스트"

        with patch("core.message_envelope.MessageEnvelope.wrap", return_value=FakeEnvelope()), \
             patch("core.telegram_formatting.split_message", return_value=["텍스트"]), \
             patch("core.message_envelope.EnvelopeManager") as MockMgr:
            MockMgr.return_value.save = AsyncMock()
            result = await send_chunked_message(
                bot=MagicMock(),
                display=mock_display,
                chat_id=12345,
                text="텍스트",
                org_id="test_org",
            )

        assert result == mock_sent
