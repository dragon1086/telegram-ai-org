from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.telegram_relay import TelegramRelay


@pytest.mark.asyncio
async def test_auto_upload_uses_configured_target(tmp_path, monkeypatch):
    relay = TelegramRelay(
        token="wrong-token",
        allowed_chat_id=999,
        session_manager=AsyncMock(),
        memory_manager=AsyncMock(),
        org_id="global",
    )

    artifact = tmp_path / "report.md"
    artifact.write_text("hello", encoding="utf-8")

    uploads: list[tuple[str, int, str, str]] = []

    monkeypatch.setattr(
        "core.telegram_relay.resolve_delivery_target",
        lambda org_id: type("T", (), {"token": "cfg-token", "chat_id": 123, "org_id": org_id})(),
    )

    async def _fake_upload(token: str, chat_id: int, file_path: str, caption: str = "") -> bool:
        uploads.append((token, chat_id, file_path, caption))
        return True

    monkeypatch.setattr("tools.telegram_uploader.upload_file", _fake_upload)

    await relay._auto_upload(f"생성됨: {artifact}", token="bad-token", chat_id=777)

    assert uploads == [("cfg-token", 123, str(artifact), f"📎 global 산출물: {artifact.name}")]


@pytest.mark.asyncio
async def test_auto_upload_skips_missing_files(monkeypatch):
    relay = TelegramRelay(
        token="fake",
        allowed_chat_id=123,
        session_manager=AsyncMock(),
        memory_manager=AsyncMock(),
        org_id="global",
    )

    monkeypatch.setattr(
        "core.telegram_relay.resolve_delivery_target",
        lambda org_id: type("T", (), {"token": "cfg-token", "chat_id": 123, "org_id": org_id})(),
    )
    upload = AsyncMock(return_value=True)
    monkeypatch.setattr("tools.telegram_uploader.upload_file", upload)

    await relay._auto_upload("생성됨: /tmp/does-not-exist.md", token="cfg-token", chat_id=123)

    upload.assert_not_awaited()
