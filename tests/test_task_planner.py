"""TaskPlanner 단위 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task_planner import ExecutionPlan, Phase, SubTask, TaskPlanner, _parse_plan


WORKERS = [
    {"name": "cokac", "engine": "claude-code", "description": "코딩, 구현, 리팩토링 전문"},
    {"name": "researcher", "engine": "codex", "description": "분석, 리서치, 데이터 처리"},
]


def _make_planner() -> TaskPlanner:
    with patch("core.task_planner.AsyncOpenAI"):
        return TaskPlanner()


def _mock_llm_response(payload: dict):
    choice = MagicMock()
    choice.message.content = json.dumps(payload, ensure_ascii=False)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# _parse_plan — 데이터 변환 검증
# ---------------------------------------------------------------------------

def test_parse_plan_single_phase():
    data = {
        "summary": "테스트 계획",
        "estimated_workers": ["cokac"],
        "phases": [
            {
                "parallel": False,
                "tasks": [{"worker_name": "cokac", "instruction": "코딩 해줘", "depends_on": []}],
            }
        ],
    }
    plan = _parse_plan(data)
    assert plan.summary == "테스트 계획"
    assert plan.estimated_workers == ["cokac"]
    assert len(plan.phases) == 1
    assert plan.phases[0].parallel is False
    assert plan.phases[0].tasks[0].worker_name == "cokac"


def test_parse_plan_parallel_phase():
    data = {
        "summary": "병렬 계획",
        "estimated_workers": ["cokac", "researcher"],
        "phases": [
            {
                "parallel": False,
                "tasks": [{"worker_name": "cokac", "instruction": "1단계", "depends_on": []}],
            },
            {
                "parallel": True,
                "tasks": [
                    {"worker_name": "cokac", "instruction": "PR 만들기", "depends_on": ["phase_0_task_0"]},
                    {"worker_name": "researcher", "instruction": "리포트 작성", "depends_on": ["phase_0_task_0"]},
                ],
            },
        ],
    }
    plan = _parse_plan(data)
    assert len(plan.phases) == 2
    assert plan.phases[1].parallel is True
    assert len(plan.phases[1].tasks) == 2


# ---------------------------------------------------------------------------
# TaskPlanner.plan — LLM 성공 경로
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_llm_returns_execution_plan():
    planner = _make_planner()
    payload = {
        "summary": "다크모드 구현 후 리포트",
        "estimated_workers": ["cokac", "researcher"],
        "phases": [
            {
                "parallel": False,
                "tasks": [{"worker_name": "cokac", "instruction": "다크모드 구현", "depends_on": []}],
            },
            {
                "parallel": True,
                "tasks": [
                    {"worker_name": "cokac", "instruction": "PR 생성", "depends_on": ["phase_0_task_0"]},
                    {"worker_name": "researcher", "instruction": "분석 리포트 작성", "depends_on": ["phase_0_task_0"]},
                ],
            },
        ],
    }
    planner.client.chat.completions.create = AsyncMock(return_value=_mock_llm_response(payload))

    plan = await planner.plan("prism-mobile 다크모드 + 분석 리포트 동시에 만들어줘", WORKERS)

    assert isinstance(plan, ExecutionPlan)
    assert len(plan.phases) == 2
    assert plan.phases[0].parallel is False
    assert plan.phases[1].parallel is True
    assert plan.phases[1].tasks[0].worker_name == "cokac"
    assert plan.phases[1].tasks[1].worker_name == "researcher"


# ---------------------------------------------------------------------------
# TaskPlanner.plan — 워커 없음 → 빈 계획
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_no_workers_returns_empty():
    planner = _make_planner()
    planner.client.chat.completions.create = AsyncMock()

    plan = await planner.plan("뭔가 해줘", [])

    assert plan.phases == []
    planner.client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# TaskPlanner.plan — LLM 실패 → 폴백 계획
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_llm_failure_uses_fallback():
    planner = _make_planner()
    planner.client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

    plan = await planner.plan("코딩 해줘", WORKERS)

    assert isinstance(plan, ExecutionPlan)
    assert len(plan.phases) == 1
    assert plan.phases[0].parallel is False
    assert plan.phases[0].tasks[0].worker_name == WORKERS[0]["name"]


# ---------------------------------------------------------------------------
# _fallback_plan — 구조 검증
# ---------------------------------------------------------------------------

def test_fallback_plan_structure():
    planner = _make_planner()
    plan = planner._fallback_plan("어떤 작업", WORKERS)

    assert len(plan.phases) == 1
    assert plan.phases[0].parallel is False
    assert len(plan.phases[0].tasks) == 1
    assert plan.phases[0].tasks[0].worker_name == WORKERS[0]["name"]
    assert "어떤 작업" in plan.phases[0].tasks[0].instruction
