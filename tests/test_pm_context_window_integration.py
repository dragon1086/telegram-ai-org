"""PM 오케스트레이터 — 대화 이력 컨텍스트 주입 통합 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.pm_orchestrator import PMOrchestrator, RequestPlan
from core.context_window import format_history_for_prompt, build_context_window


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_history(n: int = 5) -> list[dict]:
    """최신 순(DESC) 대화 이력 생성."""
    msgs = []
    for i in range(n - 1, -1, -1):
        msgs.append({
            "content": f"{'사용자' if i % 2 == 0 else 'PM'} 메시지 {i}",
            "role": "user" if i % 2 == 0 else "bot",
            "is_bot": i % 2 != 0,
            "timestamp": f"2026-01-01T{i:02d}:00:00",
        })
    return msgs


def _make_orchestrator(decision_client=None) -> PMOrchestrator:
    db = MagicMock()
    db.get_pm_task = AsyncMock(return_value=None)
    graph = MagicMock()
    claim = MagicMock()
    memory = MagicMock()
    memory.search_memories = AsyncMock(return_value=[])
    memory.build_context = MagicMock(return_value="")
    send_fn = AsyncMock()
    return PMOrchestrator(
        context_db=db,
        task_graph=graph,
        claim_manager=claim,
        memory=memory,
        org_id="aiorg_pm_bot",
        telegram_send_func=send_fn,
        decision_client=decision_client,
    )


# ── build_context_window 통합 검증 ───────────────────────────────────────────

def test_build_context_window_respects_max_messages():
    history = _make_history(20)
    result = build_context_window(history, max_messages=5, max_tokens=50000)
    assert len(result) <= 5


def test_build_context_window_asc_order():
    history = _make_history(5)
    result = build_context_window(history, max_messages=10, max_tokens=50000)
    ts_list = [r["timestamp"] for r in result]
    assert ts_list == sorted(ts_list)


def test_build_context_window_50_turns_token_guard():
    """50턴 초과 시 토큰 한도 내에서만 포함."""
    history = _make_history(50)
    result = build_context_window(history, max_messages=10, max_tokens=2000)
    from core.context_window import estimate_tokens
    total = sum(estimate_tokens(str(m.get("content", ""))) for m in result)
    assert total <= 2000
    assert len(result) <= 10


# ── format_history_for_prompt ─────────────────────────────────────────────────

def test_format_history_included_in_decompose_prompt():
    """_build_decompose_prompt에 prior context가 포함되는지 검증."""
    orch = _make_orchestrator()
    history = _make_history(3)
    prompt = orch._build_decompose_prompt(
        "PM 봇 개선해줘", [], conversation_history=history
    )
    assert "[CONTEXT]" in prompt
    assert "[/CONTEXT]" in prompt


def test_format_history_not_in_prompt_when_empty():
    """빈 이력이면 CONTEXT 블록이 포함되지 않아야 함."""
    orch = _make_orchestrator()
    prompt = orch._build_decompose_prompt(
        "PM 봇 개선해줘", [], conversation_history=[]
    )
    assert "[CONTEXT]" not in prompt


def test_format_history_none_history_graceful():
    """conversation_history=None 시 crash 없이 프롬프트 생성."""
    orch = _make_orchestrator()
    prompt = orch._build_decompose_prompt(
        "PM 봇 개선해줘", [], conversation_history=None
    )
    assert "PM 봇 개선해줘" in prompt


# ── plan_request API 호환성 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plan_request_without_history_still_works():
    """history 없이 기존 방식으로 호출해도 동작해야 함 (하위 호환)."""
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value='{"lane":"direct_answer","route":"direct_reply","complexity":"low","rationale":"테스트"}')
    orch = _make_orchestrator(decision_client=mock_client)

    with patch.object(orch, "_detect_relevant_depts", return_value=[]):
        with patch.object(orch, "_extract_workdir", return_value=None):
            plan = await orch.plan_request("안녕")  # history 미전달
    assert plan is not None


@pytest.mark.asyncio
async def test_plan_request_with_history_injects_context():
    """history 전달 시 LLM 프롬프트에 CONTEXT 블록이 포함되어야 함."""
    captured_prompts: list[str] = []

    async def mock_complete(prompt: str, **kwargs) -> str:
        captured_prompts.append(prompt)
        return '{"lane":"direct_answer","route":"direct_reply","complexity":"low","rationale":"테스트"}'

    mock_client = MagicMock()
    mock_client.complete = mock_complete
    orch = _make_orchestrator(decision_client=mock_client)

    history = _make_history(5)
    with patch.object(orch, "_detect_relevant_depts", return_value=[]):
        with patch.object(orch, "_extract_workdir", return_value=None):
            await orch.plan_request("PM 봇 개선", conversation_history=history)

    assert len(captured_prompts) == 1
    assert "[CONTEXT]" in captured_prompts[0]
    assert "[/CONTEXT]" in captured_prompts[0]


@pytest.mark.asyncio
async def test_decompose_with_history_injects_context():
    """decompose 호출 시 history가 분해 프롬프트에 포함되어야 함."""
    captured_prompts: list[str] = []

    async def mock_complete(prompt: str, **kwargs) -> str:
        captured_prompts.append(prompt)
        return "DEPT:aiorg_engineering_bot|TASK:PM 봇 컨텍스트 개선|DEPENDS:none"

    mock_client = MagicMock()
    mock_client.complete = mock_complete
    orch = _make_orchestrator(decision_client=mock_client)

    history = _make_history(5)
    with patch.object(orch, "_dept_map", return_value={"aiorg_engineering_bot": "개발실"}):
        with patch.object(orch, "_dept_profiles", return_value={
            "aiorg_engineering_bot": {"dept_name": "개발실", "role": "개발", "specialties": []}
        }):
            with patch.object(orch, "_detect_relevant_depts", return_value=["aiorg_engineering_bot"]):
                with patch.object(orch, "_extract_workdir", return_value=None):
                    subtasks = await orch.decompose("PM 봇 개선", conversation_history=history)

    assert len(captured_prompts) >= 1
    assert "[CONTEXT]" in captured_prompts[0]
    assert len(subtasks) == 1


@pytest.mark.asyncio
async def test_decompose_without_history_still_works():
    """history 없이 기존 방식 호출 시에도 정상 동작."""
    async def mock_complete(prompt: str, **kwargs) -> str:
        return "DEPT:aiorg_engineering_bot|TASK:기존 방식 테스트|DEPENDS:none"

    mock_client = MagicMock()
    mock_client.complete = mock_complete
    orch = _make_orchestrator(decision_client=mock_client)

    with patch.object(orch, "_dept_map", return_value={"aiorg_engineering_bot": "개발실"}):
        with patch.object(orch, "_dept_profiles", return_value={
            "aiorg_engineering_bot": {"dept_name": "개발실", "role": "개발", "specialties": []}
        }):
            with patch.object(orch, "_detect_relevant_depts", return_value=[]):
                with patch.object(orch, "_extract_workdir", return_value=None):
                    subtasks = await orch.decompose("PM 봇 개선")  # history 없이

    assert len(subtasks) == 1
