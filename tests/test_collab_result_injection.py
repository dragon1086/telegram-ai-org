from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.telegram_relay import TelegramRelay


def _make_relay(org_id: str = "pm-bot") -> TelegramRelay:
    relay = object.__new__(TelegramRelay)
    relay.org_id = org_id
    relay._collab_injecting = set()
    relay._uploaded_artifacts = set()
    relay.context_db = AsyncMock()
    relay.context_db.update_pm_task_metadata = AsyncMock()
    return relay


def _collab_task(
    task_id: str = "T-001",
    collab_requester: str = "cokac",
    result: str = "분석 완료",
    result_injected: bool = False,
) -> dict:
    return {
        "task_id": task_id,
        "description": "collab task desc",
        "result": result,
        "status": "done",
        "metadata": {
            "collab": True,
            "collab_requester": collab_requester,
            "result_injected": result_injected,
        },
    }


@pytest.mark.asyncio
async def test_inject_collab_result_happy_path():
    """Result is sent to requester org's chat."""
    relay = _make_relay("pm-bot")
    task = _collab_task()

    fake_org = MagicMock()
    fake_org.token = "requester-token"
    fake_org.chat_id = 12345

    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()

    with patch("core.orchestration_config.load_orchestration_config") as mock_cfg, \
         patch("telegram.Bot", return_value=fake_bot):
        mock_cfg.return_value.get_org.return_value = fake_org
        await relay._inject_collab_result(task)

    fake_bot.send_message.assert_awaited_once()
    args = fake_bot.send_message.call_args
    assert args[1]["chat_id"] == 12345
    assert "분석 완료" in args[1]["text"]
    relay.context_db.update_pm_task_metadata.assert_awaited_once_with(
        "T-001", {"result_injected": True}
    )


@pytest.mark.asyncio
async def test_inject_collab_result_idempotent():
    """Already-injected task is skipped."""
    relay = _make_relay()
    task = _collab_task(result_injected=True)

    with patch("core.telegram_relay.load_orchestration_config"), \
         patch("telegram.Bot") as mock_bot_cls:
        await relay._inject_collab_result(task)

    mock_bot_cls.assert_not_called()
    relay.context_db.update_pm_task_metadata.assert_not_awaited()


@pytest.mark.asyncio
async def test_inject_collab_result_skips_non_collab():
    """Task without collab=True is silently skipped."""
    relay = _make_relay()
    task = {
        "task_id": "T-002",
        "description": "normal task",
        "result": "done",
        "metadata": {"collab": False},
    }

    with patch("telegram.Bot") as mock_bot_cls:
        await relay._inject_collab_result(task)

    mock_bot_cls.assert_not_called()


@pytest.mark.asyncio
async def test_inject_collab_result_missing_org_config():
    """Missing org config logs warning, no exception raised."""
    relay = _make_relay()
    task = _collab_task()

    with patch("core.orchestration_config.load_orchestration_config") as mock_cfg, \
         patch("telegram.Bot") as mock_bot_cls:
        mock_cfg.return_value.get_org.return_value = None
        # Should NOT raise
        await relay._inject_collab_result(task)

    mock_bot_cls.assert_not_called()
    relay.context_db.update_pm_task_metadata.assert_not_awaited()


@pytest.mark.asyncio
async def test_inject_collab_result_triggered_by_pm_done_event(monkeypatch):
    """_handle_pm_done_event fires asyncio.create_task for collab injection."""
    relay = _make_relay()
    task_id = "T-aiorg_pm_bot-099"
    relay.context_db = AsyncMock()
    relay.context_db.get_pm_task = AsyncMock(return_value=_collab_task(task_id))
    relay.context_db.get_subtasks = AsyncMock(return_value=[])
    relay._synthesizing = set()
    relay._collab_injecting = set()
    relay._uploaded_artifacts = set()

    # _handle_pm_done_event parses task_id from text like "태스크 T-xxx 완료"
    done_text = f"✅ 태스크 {task_id} 완료"

    created_tasks: list = []

    def fake_create_task(coro):
        created_tasks.append(coro)
        # Don't actually schedule — just record it was called
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    with patch("asyncio.create_task", side_effect=fake_create_task), \
         patch.object(relay, "_inject_collab_result", return_value=None) as mock_inject:
        try:
            await relay._handle_pm_done_event(done_text)
        except Exception:
            pass

    assert len(created_tasks) >= 1, "asyncio.create_task was not called"
    mock_inject.assert_called()


@pytest.mark.asyncio
async def test_inject_collab_result_uploads_artifacts_to_requester_org(tmp_path):
    """_upload_artifacts_to is called with requester's token/chat_id, not PM bot's own."""
    relay = _make_relay("pm-bot")
    relay.context_db.update_pm_task_metadata = AsyncMock()

    report = tmp_path / "report.md"
    report.write_text("# 결과")
    task = _collab_task(result=f"완료\n[ARTIFACT:{report}]")

    fake_org = MagicMock()
    fake_org.token = "requester-token-xyz"
    fake_org.chat_id = 99999

    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()

    with patch("core.orchestration_config.load_orchestration_config") as mock_cfg, \
         patch("telegram.Bot", return_value=fake_bot), \
         patch.object(relay, "_upload_artifacts_to", new_callable=AsyncMock) as mock_upload:
        mock_cfg.return_value.get_org.return_value = fake_org
        await relay._inject_collab_result(task)

    mock_upload.assert_awaited_once()
    upload_args = mock_upload.call_args
    assert upload_args[0][1] == "requester-token-xyz"   # token
    assert upload_args[0][2] == 99999                    # chat_id
