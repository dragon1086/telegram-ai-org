"""interaction_mode 자동 감지 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.pm_orchestrator import PMOrchestrator, RequestPlan


# ── _classify_interaction_mode 단위 테스트 ────────────────────────────────────

def test_classify_debate_lane():
    mode = PMOrchestrator._classify_interaction_mode("debate", "delegate", "토론해봐")
    assert mode == "debate"


def test_classify_delegate_multi_org():
    mode = PMOrchestrator._classify_interaction_mode(
        "multi_org_execution", "delegate", "여러 팀에서 만들어줘"
    )
    assert mode == "delegate"


def test_classify_discussion_keywords():
    mode = PMOrchestrator._classify_interaction_mode(
        "multi_org_execution", "delegate", "봇들끼리 얘기해봐"
    )
    assert mode == "discussion"


def test_classify_direct_single_org():
    mode = PMOrchestrator._classify_interaction_mode(
        "single_org_execution", "local_execution", "개발해줘"
    )
    assert mode == "direct"


def test_classify_direct_answer():
    mode = PMOrchestrator._classify_interaction_mode(
        "direct_answer", "direct_reply", "현황 알려줘"
    )
    assert mode == "direct"


def test_classify_clarify():
    mode = PMOrchestrator._classify_interaction_mode(
        "clarify", "direct_reply", "무슨 뜻이야"
    )
    assert mode == "direct"


def test_classify_review_or_audit():
    mode = PMOrchestrator._classify_interaction_mode(
        "review_or_audit", "local_execution", "코드 리뷰해줘"
    )
    assert mode == "direct"


def test_classify_attachment_analysis():
    mode = PMOrchestrator._classify_interaction_mode(
        "attachment_analysis", "local_execution", "이 파일 분석해줘"
    )
    assert mode == "direct"


# ── RequestPlan 기본값 테스트 ──────────────────────────────────────────────────

def test_request_plan_default_interaction_mode():
    plan = RequestPlan(
        lane="single_org_execution",
        route="local_execution",
        complexity="low",
        rationale="test",
    )
    assert plan.interaction_mode == "direct"


# ── heuristic 경로 통합 테스트 ────────────────────────────────────────────────

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
        decision_client=None,  # heuristic fallback 강제
    )


@pytest.mark.asyncio
async def test_direct_mode_heuristic(orchestrator):
    plan = await orchestrator.plan_request("개발해줘")
    assert plan.interaction_mode == "direct"


@pytest.mark.asyncio
async def test_delegate_mode_heuristic(orchestrator):
    plan = await orchestrator.plan_request("여러 조직이 기획하고 개발하고 마케팅해줘")
    assert plan.interaction_mode == "delegate"


@pytest.mark.asyncio
async def test_debate_mode_heuristic(orchestrator):
    plan = await orchestrator.plan_request("토론해봐")
    assert plan.interaction_mode == "debate"
    assert plan.lane == "debate"


@pytest.mark.asyncio
async def test_discussion_mode_heuristic(orchestrator):
    plan = await orchestrator.plan_request("봇들끼리 얘기해봐")
    assert plan.interaction_mode == "discussion"


@pytest.mark.asyncio
async def test_non_debate_regression(orchestrator):
    plan = await orchestrator.plan_request("개발해줘")
    assert plan.interaction_mode != "debate"
    assert plan.lane != "debate"
