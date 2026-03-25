from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.telegram_relay import TelegramRelay


@pytest.mark.asyncio
async def test_handle_collab_tags_dispatches_real_request() -> None:
    relay = TelegramRelay(
        token="fake",
        allowed_chat_id=123,
        session_manager=MagicMock(),
        memory_manager=MagicMock(),
        org_id="aiorg_engineering_bot",
        context_db=None,
    )
    relay._infer_collab_target_mentions = MagicMock(return_value=["@aiorg_design_bot"])
    relay._org_mention = MagicMock(return_value="@aiorg_engineering_bot")
    relay.display.send_to_chat = AsyncMock()

    response = (
        "[TEAM:solo]\n"
        "설계 검토가 필요합니다. "
        "[COLLAB:로그인 화면 UX 리뷰 필요|맥락: 인증 플로우 와이어프레임 초안]"
    )

    cleaned = await relay._handle_collab_tags(
        response,
        bot=SimpleNamespace(),
        chat_id=123,
        requester_mention="@rocky",
        reply_to_message_id=77,
    )

    assert "로그인 화면 UX 리뷰 필요" not in cleaned
    relay.display.send_to_chat.assert_awaited_once()
    sent_text = relay.display.send_to_chat.await_args.args[2]
    assert "🙋 도와줄 조직 찾아요!" in sent_text
    assert "요청자: @rocky" in sent_text
    assert "대상조직: @aiorg_design_bot" in sent_text
    assert "📎 맥락: 인증 플로우 와이어프레임 초안" in sent_text


@pytest.mark.asyncio
async def test_handle_collab_tags_ignores_placeholder_request() -> None:
    relay = TelegramRelay(
        token="fake",
        allowed_chat_id=123,
        session_manager=MagicMock(),
        memory_manager=MagicMock(),
        org_id="aiorg_product_bot",
        context_db=None,
    )
    relay._infer_collab_target_mentions = MagicMock(return_value=["@aiorg_growth_bot"])
    relay._org_mention = MagicMock(return_value="@aiorg_product_bot")
    relay.display.send_to_chat = AsyncMock()

    response = (
        "[TEAM:solo]\n"
        "[COLLAB:구체적 작업 설명|맥락: 현재 작업 요약]\n"
        "최종 요약입니다."
    )

    cleaned = await relay._handle_collab_tags(
        response,
        bot=SimpleNamespace(),
        chat_id=123,
        requester_mention="@rocky",
    )

    # [TEAM:solo] 태그는 팀 헤더로 변환돼 cleaned 앞에 붙고,
    # 플레이스홀더 [COLLAB:...]는 드롭된다 — 핵심 내용 포함 여부만 검증
    assert "최종 요약입니다." in cleaned
    relay.display.send_to_chat.assert_not_called()
