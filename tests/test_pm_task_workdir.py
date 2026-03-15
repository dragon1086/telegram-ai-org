from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.telegram_relay import TelegramRelay


@pytest.mark.asyncio
async def test_execute_pm_task_passes_workdir_to_runner() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = ContextDB(Path(tmp) / "test.db")
        await db.initialize()
        await db.create_pm_task(
            "T-1",
            "외부 리포지토리 수정",
            "aiorg_engineering_bot",
            "pm",
            metadata={"workdir": "/tmp/openclaw"},
        )
        task_info = await db.get_pm_task("T-1")
        assert task_info is not None

        relay = TelegramRelay(
            token="fake",
            allowed_chat_id=123,
            session_manager=MagicMock(),
            memory_manager=MagicMock(),
            org_id="aiorg_engineering_bot",
            context_db=db,
        )
        relay.identity.build_system_prompt = MagicMock(return_value="system")
        relay.display.send_to_chat = AsyncMock()
        relay.app = MagicMock()
        relay.app.bot = MagicMock()
        relay._auto_upload = AsyncMock()

        relay._execute_with_team_config = AsyncMock(return_value="완료")
        relay._build_team_config = AsyncMock(return_value=MagicMock())

        await relay._execute_pm_task(task_info)

        assert relay._execute_with_team_config.await_args.kwargs["workdir"] == "/tmp/openclaw"
