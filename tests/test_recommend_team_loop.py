"""Tests for recommend_team feedback loop in PMOrchestrator."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, AsyncMock


def test_task_type_vocab_defined():
    from core.agent_persona_memory import TASK_TYPE_VOCAB
    assert isinstance(TASK_TYPE_VOCAB, frozenset)
    assert "coding" in TASK_TYPE_VOCAB
    assert "general" in TASK_TYPE_VOCAB


def test_infer_task_type_coding():
    from core.pm_orchestrator import PMOrchestrator
    # Create minimal instance without full init
    orch = object.__new__(PMOrchestrator)
    result = orch._infer_task_type("코드 수정해줘")
    assert result == "coding"


def test_infer_task_type_research():
    from core.pm_orchestrator import PMOrchestrator
    orch = object.__new__(PMOrchestrator)
    result = orch._infer_task_type("시장 조사 해줘")
    assert result == "research"


def test_infer_task_type_general():
    from core.pm_orchestrator import PMOrchestrator
    orch = object.__new__(PMOrchestrator)
    result = orch._infer_task_type("안녕 잘 지내?")
    assert result == "general"


def test_infer_task_type_vocab_alignment():
    """All return values of _infer_task_type are members of TASK_TYPE_VOCAB."""
    from core.pm_orchestrator import PMOrchestrator
    from core.agent_persona_memory import TASK_TYPE_VOCAB
    orch = object.__new__(PMOrchestrator)
    test_messages = [
        "코드 짜줘", "디자인 해줘", "리서치", "기획서", "배포해줘",
        "마케팅", "안녕", "hello world", "테스트 작성",
    ]
    for msg in test_messages:
        result = orch._infer_task_type(msg)
        assert result in TASK_TYPE_VOCAB, f"'{result}' not in TASK_TYPE_VOCAB for msg: '{msg}'"


@pytest.mark.asyncio
async def test_plan_request_no_recommend_on_empty_hints():
    """When dept_hints is empty, recommend_team should NOT be called."""
    from core.pm_orchestrator import PMOrchestrator
    orch = object.__new__(PMOrchestrator)
    orch._apm = MagicMock()
    orch._apm.recommend_team = MagicMock(return_value=[])
    orch._detect_relevant_depts = MagicMock(return_value=[])  # empty hints
    orch._extract_workdir = MagicMock(return_value=None)
    orch._llm_unified_classify = AsyncMock(return_value=MagicMock(
        lane="direct_answer", route="direct_reply", complexity="low",
        rationale="test", dept_hints=[], confidence=1.0,
    ))
    orch._normalize_request_plan = MagicMock(return_value=MagicMock())

    await orch.plan_request("안녕")
    orch._apm.recommend_team.assert_not_called()
