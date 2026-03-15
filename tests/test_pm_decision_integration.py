from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.claim_manager import ClaimManager
from core.context_db import ContextDB
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator
from core.pm_router import PMRouter
from core.task_graph import TaskGraph


class _FakeDecisionClient:
    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        workdir: str | None = None,
    ) -> str:
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "workdir": workdir,
        })
        if not self._responses:
            raise AssertionError("fake decision client exhausted")
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_pm_router_prefers_decision_client(monkeypatch):
    monkeypatch.setattr(
        "core.pm_router.PMRouter._get_provider",
        lambda self: (_ for _ in ()).throw(AssertionError("provider should not be loaded")),
    )
    client = _FakeDecisionClient('{"action":"status_query","task_id":null,"confidence":0.91}')
    router = PMRouter(decision_client=client)

    route = await router.route("지금 상태 어때?", {"pending_confirmation": None})

    assert route.action == "status_query"
    assert client.calls


@pytest.mark.asyncio
async def test_pm_orchestrator_plan_request_uses_decision_client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "core.pm_orchestrator.get_provider",
        lambda: (_ for _ in ()).throw(AssertionError("provider should not be loaded")),
    )
    db = ContextDB(tmp_path / "test.db")
    await db.initialize()
    client = _FakeDecisionClient(
        '{"route":"delegate","complexity":"high","rationale":"복수 조직 협업 필요","confidence":0.93}'
    )
    orch = PMOrchestrator(
        context_db=db,
        task_graph=TaskGraph(db),
        claim_manager=ClaimManager(),
        memory=MemoryManager("global"),
        org_id="global",
        telegram_send_func=AsyncMock(),
        decision_client=client,
    )

    plan = await orch.plan_request(f"{tmp_path} 에서 새 기능을 기획하고 디자인하고 개발해줘")

    assert plan.route == "delegate"
    assert client.calls[0]["workdir"] == str(tmp_path)


@pytest.mark.asyncio
async def test_pm_orchestrator_decompose_uses_decision_client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "core.pm_orchestrator.get_provider",
        lambda: (_ for _ in ()).throw(AssertionError("provider should not be loaded")),
    )
    db = ContextDB(tmp_path / "test.db")
    await db.initialize()
    client = _FakeDecisionClient(
        "\n".join([
            "DEPT:aiorg_product_bot|TASK:요구사항을 정리하고 PRD 초안을 작성하세요|DEPENDS:none",
            "DEPT:aiorg_engineering_bot|TASK:PRD 기준으로 구현 범위를 정리하세요|DEPENDS:0",
        ])
    )
    orch = PMOrchestrator(
        context_db=db,
        task_graph=TaskGraph(db),
        claim_manager=ClaimManager(),
        memory=MemoryManager("global"),
        org_id="global",
        telegram_send_func=AsyncMock(),
        decision_client=client,
    )

    subtasks = await orch.decompose(f"{tmp_path} 에서 새 기능을 기획하고 개발해줘")

    assert [task.assigned_dept for task in subtasks] == [
        "aiorg_product_bot",
        "aiorg_engineering_bot",
    ]
    assert client.calls[0]["workdir"] == str(tmp_path)
