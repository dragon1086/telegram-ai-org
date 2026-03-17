"""Collab E2E 테스트 — dispatch → completion → synthesis 흐름 검증."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pm_orchestrator import PMOrchestrator
from core.telegram_relay import TelegramRelay


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────


class _FakeOrg:
    def __init__(self, org_id: str, dept_name: str = "", direction: str = ""):
        self.id = org_id
        self.dept_name = dept_name
        self.direction = direction


class _FakeConfig:
    def list_orgs(self):
        return [
            _FakeOrg("aiorg_dev", "개발팀", "소프트웨어 개발"),
            _FakeOrg("aiorg_mkt", "마케팅팀", "마케팅 전략"),
        ]

    def get_org(self, org_id: str):  # noqa: D102
        for org in self.list_orgs():
            if org.id == org_id:
                return org
        return None


def _make_orchestrator(org_id: str = "aiorg_pm") -> PMOrchestrator:
    """최소 mock으로 PMOrchestrator 인스턴스 생성."""
    db = MagicMock()
    graph = MagicMock()
    claim = MagicMock()
    memory = MagicMock()
    orch = PMOrchestrator(
        context_db=db,
        task_graph=graph,
        claim_manager=claim,
        memory=memory,
        org_id=org_id,
        telegram_send_func=AsyncMock(),
        decision_client=None,
    )
    return orch


def _make_relay(org_id: str = "aiorg_pm") -> TelegramRelay:
    """최소 mock으로 TelegramRelay 인스턴스 생성."""
    relay = object.__new__(TelegramRelay)
    relay.org_id = org_id
    relay._collab_injecting = set()
    relay._uploaded_artifacts = set()
    relay.context_db = AsyncMock()
    relay.context_db.update_pm_task_metadata = AsyncMock()
    return relay


# ── TC1: collab_dispatch → create_pm_task + task_id 반환 ─────────────────────


@pytest.mark.asyncio
async def test_collab_dispatch_creates_parent_and_subtask():
    """collab_dispatch 호출 시 collab 메타데이터가 포함된 pm_task가 생성된다."""
    orch = _make_orchestrator()
    orch._db.create_pm_task = AsyncMock()
    orch._next_task_id = AsyncMock(return_value="task-collab-001")

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=_FakeConfig()):
        result = await orch.collab_dispatch(
            parent_task_id="parent-1",
            task="도움요청",
            target_org="aiorg_dev",
            requester_org="aiorg_mkt",
            chat_id=123,
        )

    orch._db.create_pm_task.assert_awaited_once()
    kwargs = orch._db.create_pm_task.call_args.kwargs
    meta = kwargs["metadata"]
    assert meta.get("collab") is True
    assert meta.get("collab_requester") == "aiorg_mkt"
    assert isinstance(result, str) and len(result) > 0


# ── TC2: _inject_collab_result → requester chat에 결과 전송 ───────────────────


@pytest.mark.asyncio
async def test_collab_result_injection():
    """_inject_collab_result 호출 시 collab_requester_chat_id로 결과가 전송된다."""
    relay = _make_relay()

    # collab_requester_chat_id 방식으로 직접 chat_id를 메타데이터에 넣는다
    task_info = {
        "task_id": "T-collab-002",
        "description": "collab task",
        "result": "결과물",
        "status": "done",
        "metadata": {
            "collab": True,
            "collab_requester": "aiorg_mkt",
            "result_injected": False,
        },
    }

    fake_org = MagicMock()
    fake_org.token = "fake-token"
    fake_org.chat_id = 456

    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()

    with patch("core.orchestration_config.load_orchestration_config") as mock_cfg, \
         patch("telegram.Bot", return_value=fake_bot):
        mock_cfg.return_value.get_org.return_value = fake_org
        await relay._inject_collab_result(task_info)

    fake_bot.send_message.assert_awaited_once()
    call_kwargs = fake_bot.send_message.call_args[1]
    assert call_kwargs["chat_id"] == 456
    assert "결과물" in call_kwargs["text"]


# ── TC3: on_task_complete → 모든 siblings done → _synthesize_and_act 호출 ────


@pytest.mark.asyncio
async def test_collab_result_triggers_synthesis():
    """서브태스크 완료 후 siblings 모두 done이면 _synthesize_and_act가 호출된다."""
    orch = _make_orchestrator()

    sibling_done = {
        "task_id": "sub-1",
        "status": "done",
        "parent_id": "parent-2",
        "result": "완료",
    }
    task_info = {
        "task_id": "sub-1",
        "parent_id": "parent-2",
        "status": "done",
        "result": "완료",
    }

    orch._db.update_pm_task_status = AsyncMock()
    orch._db.get_pm_task = AsyncMock(return_value=task_info)
    orch._db.get_subtasks = AsyncMock(return_value=[sibling_done])
    orch._graph.mark_complete = AsyncMock(return_value=[])
    orch._synthesize_and_act = AsyncMock()

    await orch.on_task_complete(task_id="sub-1", result="완료", chat_id=123)

    orch._synthesize_and_act.assert_awaited_once()
    call_args = orch._synthesize_and_act.call_args
    assert call_args[0][0] == "parent-2"


# ── TC4: end-to-end — dispatch → completion → synthesis → send ───────────────


@pytest.mark.asyncio
async def test_collab_end_to_end_flow():
    """dispatch → subtask 완료 → synthesis → _send 호출 전체 흐름을 검증한다."""
    orch = _make_orchestrator()

    # dispatch 단계
    orch._db.create_pm_task = AsyncMock()
    orch._next_task_id = AsyncMock(return_value="T-e2e-003")

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=_FakeConfig()):
        task_id = await orch.collab_dispatch(
            parent_task_id="parent-e2e",
            task="E2E 테스트 요청",
            target_org="aiorg_dev",
            requester_org="aiorg_mkt",
            chat_id=789,
        )

    assert task_id == "T-e2e-003"

    # completion 단계 — sibling 모두 done → synthesis 호출
    sibling = {"task_id": task_id, "status": "done", "result": "E2E 결과"}
    parent_task = {"task_id": "parent-e2e", "parent_id": None, "description": "E2E 테스트 요청"}

    orch._db.update_pm_task_status = AsyncMock()
    orch._db.get_pm_task = AsyncMock(side_effect=lambda tid: {
        task_id: {
            "task_id": task_id,
            "parent_id": "parent-e2e",
            "status": "done",
            "result": "E2E 결과",
        },
        "parent-e2e": parent_task,
    }.get(tid))
    orch._db.get_subtasks = AsyncMock(return_value=[sibling])
    orch._graph.mark_complete = AsyncMock(return_value=[])
    orch._synthesize_and_act = AsyncMock()

    await orch.on_task_complete(task_id=task_id, result="E2E 결과", chat_id=789)

    orch._synthesize_and_act.assert_awaited_once()
    synth_call = orch._synthesize_and_act.call_args
    assert synth_call[0][0] == "parent-e2e"
    subtasks_arg = synth_call[0][1]
    assert any(s.get("result") == "E2E 결과" for s in subtasks_arg)
