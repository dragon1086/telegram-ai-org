"""PMOrchestrator.plan_request() prior_context 주입 통합 테스트."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.claim_manager import ClaimManager
from core.context_db import ContextDB
from core.context_window import build_context_window, format_history_for_prompt
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator
from core.task_graph import TaskGraph

# ── 픽스처 ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def orch_setup():
    with tempfile.TemporaryDirectory() as tmp:
        db = ContextDB(Path(tmp) / "test.db")
        await db.initialize()
        graph = TaskGraph(db)
        claim = ClaimManager()
        memory = MemoryManager("pm")
        send_fn = AsyncMock()
        os.environ["AIORG_REPORT_DIR"] = str(Path(tmp) / "reports")
        orch = PMOrchestrator(db, graph, claim, memory, "aiorg_pm_bot", send_fn)
        yield orch, db
        os.environ.pop("AIORG_REPORT_DIR", None)


# ── plan_request 시그니처 테스트 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plan_request_accepts_prior_context(orch_setup):
    """plan_request가 prior_context 키워드 인자를 받아야 한다."""
    orch, _ = orch_setup
    # LLM 없이 heuristic으로 동작하도록 decision_client=None
    assert orch._decision_client is None

    # prior_context 없이 호출 (기존 방식 하위 호환)
    plan_no_ctx = await orch.plan_request("API 개발해줘")
    assert plan_no_ctx is not None

    # prior_context 있게 호출 (새 방식)
    ctx = "[CONTEXT]\n[user] 이전 대화\n[/CONTEXT]"
    plan_with_ctx = await orch.plan_request("구현해달라는 소리야", prior_context=ctx)
    assert plan_with_ctx is not None


@pytest.mark.asyncio
async def test_plan_request_empty_prior_context_graceful_fallback(orch_setup):
    """prior_context=""이면 기존 동작과 동일하게 동작해야 한다."""
    orch, _ = orch_setup
    plan = await orch.plan_request("간단한 질문이야", prior_context="")
    assert plan.route in {"direct_reply", "local_execution", "delegate"}


@pytest.mark.asyncio
async def test_plan_request_with_decision_client_injects_context(orch_setup):
    """decision_client가 있을 때 prior_context가 프롬프트에 포함되는지 확인."""
    orch, _ = orch_setup

    captured_prompts: list[str] = []

    async def mock_complete(prompt: str, **kwargs) -> str:
        captured_prompts.append(prompt)
        return '{"lane":"single_org_execution","route":"delegate","complexity":"medium","rationale":"테스트","confidence":0.8}'

    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.complete = mock_complete
    orch._decision_client = mock_client

    prior = "[CONTEXT]\n[user] API 개발 제안 부탁해\n[assistant] 이런 방식이 좋을 것 같아요\n[/CONTEXT]"
    await orch.plan_request("구현해줘", prior_context=prior)

    assert len(captured_prompts) == 1
    assert "[CONTEXT]" in captured_prompts[0]
    assert "API 개발 제안 부탁해" in captured_prompts[0]


@pytest.mark.asyncio
async def test_plan_request_without_decision_client_no_crash(orch_setup):
    """decision_client=None(heuristic 모드)에서 prior_context가 있어도 크래시 없어야 한다."""
    orch, _ = orch_setup
    prior = "[CONTEXT]\n[user] 여러 메시지\n[/CONTEXT]"
    plan = await orch.plan_request("디자인해줘", prior_context=prior)
    assert plan is not None


# ── context_window + context_db 통합 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_db_history_roundtrip(orch_setup):
    """DB에 메시지를 insert하고 꺼내서 context_window를 만들 수 있어야 한다."""
    _, db = orch_setup

    # 5개 메시지 삽입 (시간 순)
    for i in range(5):
        await db.insert_conversation_message(
            msg_id=i,
            chat_id="chat_123",
            user_id="user_1",
            bot_id=None,
            role="user",
            is_bot=False,
            content=f"메시지 {i}: 이전 대화 내용",
            timestamp=f"2026-03-22T{i:02d}:00:00",
        )

    msgs = await db.get_conversation_messages(chat_id="chat_123", limit=20)
    assert len(msgs) == 5

    window = build_context_window(msgs, max_messages=10, max_tokens=5000)
    assert len(window) == 5

    prompt_ctx = format_history_for_prompt(window)
    assert "[CONTEXT]" in prompt_ctx
    assert "메시지 0" in prompt_ctx
    assert "메시지 4" in prompt_ctx


@pytest.mark.asyncio
async def test_context_db_history_excludes_current_message(orch_setup):
    """현재 메시지(msg_id)를 히스토리에서 제외하는 로직 검증."""
    _, db = orch_setup

    for i in range(3):
        await db.insert_conversation_message(
            msg_id=i,
            chat_id="chat_999",
            user_id="user_1",
            bot_id=None,
            role="user",
            is_bot=False,
            content=f"past msg {i}",
            timestamp=f"2026-03-22T0{i}:00:00",
        )

    # 현재 메시지 msg_id=2 를 제외
    raw = await db.get_conversation_messages(chat_id="chat_999", limit=20)
    filtered = [m for m in raw if m.get("msg_id") != 2]
    assert len(filtered) == 2
    assert all(m["msg_id"] != 2 for m in filtered)


# ── 환경변수 파라미터 외부화 ──────────────────────────────────────────────────

def test_env_var_max_history_messages():
    """MAX_HISTORY_MESSAGES 환경변수가 반영되는지 확인."""
    import importlib

    import core.context_window as cw

    with patch.dict(os.environ, {"MAX_HISTORY_MESSAGES": "7"}):
        importlib.reload(cw)
        assert cw.MAX_HISTORY_MESSAGES == 7

    # 원복
    importlib.reload(cw)


def test_env_var_max_history_tokens():
    """MAX_HISTORY_TOKENS 환경변수가 반영되는지 확인."""
    import importlib

    import core.context_window as cw

    with patch.dict(os.environ, {"MAX_HISTORY_TOKENS": "1500"}):
        importlib.reload(cw)
        assert cw.MAX_HISTORY_TOKENS == 1500

    importlib.reload(cw)
