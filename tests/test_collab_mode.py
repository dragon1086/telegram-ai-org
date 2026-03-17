"""Cycle 3 collab 모드 단위 테스트."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pm_orchestrator import PMOrchestrator


# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

@pytest.fixture
def orchestrator():
    db = MagicMock()
    graph = MagicMock()
    claim = MagicMock()
    memory = MagicMock()
    return PMOrchestrator(
        context_db=db,
        task_graph=graph,
        claim_manager=claim,
        memory=memory,
        org_id="test_org",
        telegram_send_func=AsyncMock(),
        decision_client=None,
    )


# ── 1. collab_dispatch: create_pm_task 호출 확인 ──────────────────────────────

class _FakeOrg:
    def __init__(self, org_id, dept_name, direction=""):
        self.id = org_id
        self.dept_name = dept_name
        self.direction = direction


class _FakeConfig:
    def list_orgs(self):
        return [
            _FakeOrg("cokac", "코딩팀", "소프트웨어 개발"),
            _FakeOrg("prism", "기획팀", "전략 기획"),
        ]


@pytest.mark.asyncio
async def test_collab_dispatch_creates_task(orchestrator):
    """collab_dispatch 호출 시 create_pm_task가 1회 호출되고 task_id가 반환된다."""
    orchestrator._db.create_pm_task = AsyncMock()
    orchestrator._next_task_id = AsyncMock(return_value="fake-task-123")

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=_FakeConfig()):
        result = await orchestrator.collab_dispatch(
            parent_task_id="p1",
            task="analyze data",
            target_org="cokac",
            requester_org="prism",
            context="ctx",
            chat_id=123,
        )

    orchestrator._db.create_pm_task.assert_awaited_once()
    call_kwargs = orchestrator._db.create_pm_task.call_args.kwargs
    assert call_kwargs["assigned_dept"] == "cokac"
    assert result == "fake-task-123"


# ── 2. collab_dispatch: metadata 포함 확인 ────────────────────────────────────

@pytest.mark.asyncio
async def test_collab_dispatch_metadata(orchestrator):
    """create_pm_task 호출 시 collab 메타데이터가 올바르게 전달된다."""
    orchestrator._db.create_pm_task = AsyncMock()
    orchestrator._next_task_id = AsyncMock(return_value="fake-task-123")

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=_FakeConfig()):
        await orchestrator.collab_dispatch(
            parent_task_id="p1",
            task="analyze data",
            target_org="cokac",
            requester_org="prism",
            context="ctx",
            chat_id=123,
        )

    call_kwargs = orchestrator._db.create_pm_task.call_args.kwargs
    metadata = call_kwargs["metadata"]
    assert metadata.get("collab") is True
    assert metadata.get("collab_requester") == "prism"


# ── 3. collab_mode_fallback: ENABLE_DISCUSSION_PROTOCOL 미설정 시 precondition ─

def test_collab_mode_fallback(monkeypatch):
    """ENABLE_DISCUSSION_PROTOCOL 미설정 시 환경 변수가 None이고,
    _classify_interaction_mode는 여전히 collab을 반환한다 (분류 자체는 relay guard와 무관).
    """
    monkeypatch.delenv("ENABLE_DISCUSSION_PROTOCOL", raising=False)
    assert os.getenv("ENABLE_DISCUSSION_PROTOCOL") is None

    mode = PMOrchestrator._classify_interaction_mode(
        "multi_org_execution", "delegate", "협업해줘"
    )
    assert mode == "collab"


# ── 4. _classify_interaction_mode: collab 키워드 분류 ────────────────────────

def test_classify_collab_mode():
    """collab 키워드가 포함된 메시지는 'collab' 모드로 분류된다."""
    assert PMOrchestrator._classify_interaction_mode(
        "multi_org_execution", "delegate", "협업해줘"
    ) == "collab"
    assert PMOrchestrator._classify_interaction_mode(
        "multi_org_execution", "delegate", "봇들이 협력"
    ) == "collab"
    assert PMOrchestrator._classify_interaction_mode(
        "multi_org_execution", "delegate", "합작"
    ) == "collab"


# ── 5. _handle_collab_tags: collab_dispatch 호출, send_to_chat 미호출 ─────────

@pytest.mark.asyncio
async def test_collab_tags_pm_dispatch():
    """[COLLAB:...] 태그가 있고 target_org 추론 성공 시 collab_dispatch가 호출되고
    display.send_to_chat은 호출되지 않는다."""
    from core.telegram_relay import TelegramRelay

    # TelegramRelay 인스턴스를 생성하지 않고 직접 mock object를 구성한다
    relay = object.__new__(TelegramRelay)
    relay.org_id = "prism"

    pm_mock = MagicMock()
    pm_mock._next_task_id = AsyncMock(return_value="task-001")
    pm_mock.collab_dispatch = AsyncMock()
    relay._pm_orchestrator = pm_mock

    relay._infer_collab_target_org = AsyncMock(return_value="cokac")

    display_mock = MagicMock()
    display_mock.send_to_chat = AsyncMock()
    relay.display = display_mock

    response = "[COLLAB: build feature |맥락: some context]"
    bot_mock = MagicMock()

    with patch("core.telegram_relay.is_placeholder_collab", return_value=False):
        await relay._handle_collab_tags(response, bot=bot_mock, chat_id=123)

    pm_mock.collab_dispatch.assert_awaited_once()
    display_mock.send_to_chat.assert_not_called()
