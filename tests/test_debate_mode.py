"""Debate/창발 모드 단위 테스트."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator


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
        yield orch, db, send_fn
        os.environ.pop("AIORG_REPORT_DIR", None)


# ── 1. lane 분류: "토론해봐" → "debate" ──────────────────────────────────────

@pytest.mark.asyncio
async def test_debate_lane_classification(orch_setup):
    orch, _db, _send = orch_setup
    result = orch._heuristic_lane("토론해봐", [])
    assert result == "debate"


# ── 2. 일반 메시지 회귀: lane != "debate" ────────────────────────────────────

@pytest.mark.asyncio
async def test_non_debate_regression(orch_setup):
    orch, _db, _send = orch_setup
    result = orch._heuristic_lane("파이썬 API 개발해줘", [])
    assert result != "debate"


# ── 3. debate_dispatch: participants 수만큼 태스크 생성 ──────────────────────

@pytest.mark.asyncio
async def test_debate_dispatch_creates_tasks(orch_setup):
    orch, db, send_fn = orch_setup

    parent_id = "T-pm-debate-root"
    await db.create_pm_task(parent_id, "AI 기술 토론해봐", None, "aiorg_pm_bot")

    participants = ["aiorg_engineering_bot", "aiorg_design_bot"]

    # org_map 조회가 없어도 동작하도록 load_orchestration_config mock
    class _FakeOrg:
        def __init__(self, org_id, dept_name, direction=""):
            self.id = org_id
            self.dept_name = dept_name
            self.direction = direction

    class _FakeConfig:
        def list_orgs(self):
            return [
                _FakeOrg("aiorg_engineering_bot", "개발실", "소프트웨어 개발 전문"),
                _FakeOrg("aiorg_design_bot", "디자인실", "UX/UI 디자인 전문"),
            ]

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=_FakeConfig()):
        task_ids = await orch.debate_dispatch(
            parent_task_id=parent_id,
            topic="AI 기술 토론해봐",
            participants=participants,
            chat_id=-123,
        )

    assert len(task_ids) == len(participants)

    # 각 태스크가 DB에 저장됐고 description에 봇별 dept_name 포함
    for tid, bot_id in zip(task_ids, participants):
        task = await db.get_pm_task(tid)
        assert task is not None
        expected_dept = "개발실" if bot_id == "aiorg_engineering_bot" else "디자인실"
        assert expected_dept in task["description"]


# ── 4. debate synthesis 라우팅 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_debate_synthesis_routing(orch_setup):
    orch, db, send_fn = orch_setup

    # 공통 parent task 생성 헬퍼
    async def _make_parent(task_id: str, metadata: dict) -> None:
        await db.create_pm_task(task_id, "토론 주제", None, "aiorg_pm_bot", metadata=metadata)

    subtasks = [
        {"assigned_to": "aiorg_engineering_bot", "result": "개발 관점 의견", "metadata": {"dept_name": "개발실"}},
        {"assigned_to": "aiorg_design_bot", "result": "디자인 관점 의견", "metadata": {"dept_name": "디자인실"}},
    ]

    # 4-a. parent_meta에 "debate": True → synthesize_debate() 호출
    debate_parent_id = "T-pm-debate-synth"
    await _make_parent(debate_parent_id, {"debate": True, "debate_topic": "AI 토론"})

    synthesize_debate_mock = AsyncMock(return_value="PM 종합 판단 결과")
    synthesize_mock = AsyncMock()

    orch._synthesizer = MagicMock()
    orch._synthesizer.synthesize_debate = synthesize_debate_mock
    orch._synthesizer.synthesize = synthesize_mock

    await orch._synthesize_and_act(debate_parent_id, subtasks, chat_id=-123)

    synthesize_debate_mock.assert_awaited_once()
    synthesize_mock.assert_not_awaited()

    # 4-b. parent_meta에 "debate" 없음 → synthesize() 호출 (회귀)
    normal_parent_id = "T-pm-normal-synth"
    await _make_parent(normal_parent_id, {})

    synthesize_debate_mock.reset_mock()
    synthesize_mock.reset_mock()

    # synthesize()는 SynthesisResult를 반환해야 하므로 적절한 mock 설정
    from core.result_synthesizer import SynthesisResult, SynthesisJudgment
    synthesize_mock.return_value = SynthesisResult(
        judgment=SynthesisJudgment.SUFFICIENT,
        summary="테스트 요약",
        unified_report="테스트 보고서",
    )

    await orch._synthesize_and_act(normal_parent_id, subtasks, chat_id=-123)

    synthesize_mock.assert_awaited_once()
    synthesize_debate_mock.assert_not_awaited()
