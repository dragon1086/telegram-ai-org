from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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

    assert uploads[0] == ("cfg-token", 123, str(artifact), f"📎 global 산출물: {artifact.name}")
    assert uploads[1][0] == "cfg-token"
    assert uploads[1][1] == 123
    assert uploads[1][2].endswith(".telegram-preview.html")


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


@pytest.mark.asyncio
async def test_pm_send_message_auto_uploads_artifact(tmp_path, monkeypatch):
    """_pm_send_message가 [ARTIFACT:path] 마커를 감지해 파일을 자동 업로드한다."""
    relay = TelegramRelay(
        token="bot-token",
        allowed_chat_id=100,
        session_manager=AsyncMock(),
        memory_manager=AsyncMock(),
        org_id="global",
    )

    artifact = tmp_path / "report.md"
    artifact.write_text("# 보고서\n\n내용", encoding="utf-8")

    # 봇 앱 mock
    fake_bot = MagicMock()
    fake_app = SimpleNamespace(bot=fake_bot)
    relay.app = fake_app

    # display.send_to_chat mock
    relay.display = MagicMock()
    relay.display.send_to_chat = AsyncMock(return_value=MagicMock())

    uploads: list[tuple[str, int, str]] = []

    monkeypatch.setattr(
        "core.telegram_relay.resolve_delivery_target",
        lambda org_id: type("T", (), {"token": "cfg-token", "chat_id": 100, "org_id": org_id})(),
    )

    async def _fake_upload(token: str, chat_id: int, file_path: str, caption: str = "") -> bool:
        uploads.append((token, chat_id, file_path))
        return True

    monkeypatch.setattr("tools.telegram_uploader.upload_file", _fake_upload)

    text = f"✅ 작업 완료!\n\n보고서를 첨부합니다.\n[ARTIFACT:{artifact}]"
    await relay._pm_send_message(chat_id=100, text=text)

    # 텍스트 메시지는 [ARTIFACT:...] 제거 후 전송
    relay.display.send_to_chat.assert_awaited_once()
    sent_text = relay.display.send_to_chat.call_args[0][2]
    assert "[ARTIFACT:" not in sent_text
    assert "보고서를 첨부합니다." in sent_text

    # 파일 업로드 호출 확인 (원본 .md + .telegram-preview.html)
    uploaded_paths = [u[2] for u in uploads]
    assert str(artifact) in uploaded_paths
    assert any(p.endswith(".telegram-preview.html") for p in uploaded_paths)
    assert all(u[0] == "cfg-token" for u in uploads)
    assert all(u[1] == 100 for u in uploads)
