"""_auto_upload 폴백 동작 — resolve_delivery_target None 시 passed token/chat_id 사용."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_auto_upload_fallback_when_no_delivery_target(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("# hello", encoding="utf-8")
    response = f"결과\n[ARTIFACT:{report}]"

    from core.telegram_relay import TelegramRelay

    relay = object.__new__(TelegramRelay)
    relay.org_id = "test-pm"
    relay._uploaded_artifacts = set()

    with patch("core.telegram_relay.resolve_delivery_target", return_value=None), \
         patch("tools.telegram_uploader.upload_file", new_callable=AsyncMock) as mock_upload:
        await relay._auto_upload(response, "BOT_TOKEN", 999)
        mock_upload.assert_called_once()
        args = mock_upload.call_args
        assert args[0][0] == "BOT_TOKEN"
        assert args[0][1] == 999
