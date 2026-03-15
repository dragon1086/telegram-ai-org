"""PMOrchestrator 단위 테스트."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator, SubTask, KNOWN_DEPTS


@pytest.fixture
async def setup():
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


@pytest.mark.asyncio
async def test_decompose_engineering_task(setup):
    orch, db, send_fn = setup
    subtasks = await orch.decompose("이 API를 개발해줘")
    assert len(subtasks) >= 1
    assert any(st.assigned_dept == "aiorg_engineering_bot" for st in subtasks)


@pytest.mark.asyncio
async def test_decompose_multi_dept(setup):
    orch, db, send_fn = setup
    subtasks = await orch.decompose("새 기능을 기획하고 디자인하고 개발해줘")
    depts = {st.assigned_dept for st in subtasks}
    assert "aiorg_product_bot" in depts
    assert "aiorg_design_bot" in depts
    assert "aiorg_engineering_bot" in depts


@pytest.mark.asyncio
async def test_decompose_no_keyword_defaults_to_product(setup, monkeypatch):
    orch, db, send_fn = setup
    subtasks = await orch.decompose("이건 뭘까요?")
    assert len(subtasks) == 1
    assert subtasks[0].assigned_dept == "aiorg_product_bot"


@pytest.mark.asyncio
async def test_plan_request_direct_reply_uses_fallback_strategy(setup, monkeypatch):
    orch, db, send_fn = setup

    plan = await orch.plan_request("이건 왜 이렇게 동작해?")

    assert plan.route == "direct_reply"
    assert plan.lane == "direct_answer"
    assert plan.complexity == "low"


@pytest.mark.asyncio
async def test_plan_request_attachment_lane(setup):
    orch, db, send_fn = setup

    plan = await orch.plan_request("첨부한 이미지와 PDF를 같이 분석해줘")

    assert plan.lane == "attachment_analysis"
    assert plan.route in {"local_execution", "delegate"}


@pytest.mark.asyncio
async def test_plan_request_review_lane(setup):
    orch, db, send_fn = setup

    plan = await orch.plan_request("최근 변경사항을 리뷰하고 문제점을 정리해줘")

    assert plan.lane == "review_or_audit"


@pytest.mark.asyncio
async def test_plan_request_local_execution_for_focused_task(setup, monkeypatch):
    orch, db, send_fn = setup

    plan = await orch.plan_request("로그인 API 버그 수정해줘")

    assert plan.route == "local_execution"
    assert plan.lane == "single_org_execution"
    assert "aiorg_engineering_bot" in plan.dept_hints


@pytest.mark.asyncio
async def test_plan_request_delegate_for_multi_org_work(setup, monkeypatch):
    orch, db, send_fn = setup

    plan = await orch.plan_request("새 기능을 기획하고 디자인하고 개발해줘")

    assert plan.route == "delegate"
    assert plan.lane == "multi_org_execution"
    assert set(plan.dept_hints) >= {
        "aiorg_product_bot",
        "aiorg_design_bot",
        "aiorg_engineering_bot",
    }


@pytest.mark.asyncio
async def test_plan_request_single_org_forces_local_execution(setup, monkeypatch):
    class _EmptyConfig:
        def list_specialist_orgs(self):
            return []

    monkeypatch.setattr("core.pm_orchestrator.load_orchestration_config", lambda force_reload=False: _EmptyConfig())
    orch, db, send_fn = setup

    plan = await orch.plan_request("기획하고 디자인하고 개발해줘")

    assert plan.route == "local_execution"


@pytest.mark.asyncio
async def test_decompose_returns_empty_without_specialists(setup, monkeypatch):
    class _EmptyConfig:
        def list_specialist_orgs(self):
            return []

    monkeypatch.setattr("core.pm_orchestrator.load_orchestration_config", lambda force_reload=False: _EmptyConfig())
    orch, db, send_fn = setup

    subtasks = await orch.decompose("기획하고 개발해줘")

    assert subtasks == []


@pytest.mark.asyncio
async def test_dispatch_creates_tasks_in_db(setup):
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(parent_id, "root task", None, "aiorg_pm_bot")
    subtasks = [
        SubTask(description="기획", assigned_dept="aiorg_product_bot"),
        SubTask(description="개발", assigned_dept="aiorg_engineering_bot", depends_on=["0"]),
    ]
    task_ids = await orch.dispatch(parent_id, subtasks, chat_id=-123)
    assert len(task_ids) == 2
    # 첫 번째 태스크(기획)는 의존성 없으므로 발송됨
    assert send_fn.call_count >= 1
    # DB에 저장 확인
    for tid in task_ids:
        task = await db.get_pm_task(tid)
        assert task is not None


@pytest.mark.asyncio
async def test_dispatch_only_sends_ready_tasks(setup):
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(parent_id, "root", None, "aiorg_pm_bot")
    subtasks = [
        SubTask(description="A", assigned_dept="aiorg_product_bot"),
        SubTask(description="B", assigned_dept="aiorg_engineering_bot", depends_on=["0"]),
    ]
    await orch.dispatch(parent_id, subtasks, chat_id=-123)
    # Only A should be sent (B depends on A)
    messages_sent = [call[0][1] for call in send_fn.call_args_list]
    assert any("aiorg_product_bot" in msg for msg in messages_sent)
    assert not any("[PM_TASK:" in msg and "aiorg_engineering_bot" in msg for msg in messages_sent)


@pytest.mark.asyncio
async def test_dispatch_mentions_target_and_preserves_reply_metadata(setup):
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(
        parent_id,
        "root",
        None,
        "aiorg_pm_bot",
        metadata={"source_message_id": 77, "requester_mention": "@rocky"},
    )
    subtasks = [SubTask(description="A", assigned_dept="aiorg_engineering_bot")]

    await orch.dispatch(parent_id, subtasks, chat_id=-123)

    pm_task_calls = [
        call for call in send_fn.call_args_list
        if "[PM_TASK:" in (call.args[1] if len(call.args) > 1 else "")
    ]
    assert pm_task_calls
    call = pm_task_calls[0]
    assert "@rocky" in call.args[1]
    assert "aiorg_engineering_bot" in call.args[1]
    assert call.kwargs["reply_to_message_id"] == 77


@pytest.mark.asyncio
async def test_dispatch_persists_subtask_workdir_metadata(setup):
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(parent_id, "root", None, "aiorg_pm_bot")
    subtasks = [
        SubTask(
            description="외부 리포 수정",
            assigned_dept="aiorg_engineering_bot",
            workdir="/tmp/openclaw",
        ),
    ]

    task_ids = await orch.dispatch(parent_id, subtasks, chat_id=-123)
    task = await db.get_pm_task(task_ids[0])

    assert task is not None
    assert task["metadata"]["workdir"] == "/tmp/openclaw"


@pytest.mark.asyncio
async def test_dispatch_persists_task_packet_metadata(setup):
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(
        parent_id,
        "루트 요청",
        None,
        "aiorg_pm_bot",
        metadata={
            "original_request": "사용자 원문 요청",
            "conversation_context": "최근 대화 맥락",
            "user_expectations": ["핵심 내용을 먼저 설명할 것"],
            "requester_mention": "@rocky",
        },
    )
    subtasks = [SubTask(description="개발 검토", assigned_dept="aiorg_engineering_bot")]

    task_ids = await orch.dispatch(parent_id, subtasks, chat_id=-123)
    task = await db.get_pm_task(task_ids[0])

    assert task is not None
    packet = task["metadata"]["task_packet"]
    assert packet["original_request"] == "사용자 원문 요청"
    assert packet["conversation_context"] == "최근 대화 맥락"
    assert packet["requester_mention"] == "@rocky"
    assert "핵심 내용을 먼저 설명할 것" in packet["user_expectations"]


@pytest.mark.asyncio
async def test_on_task_complete_triggers_next(setup):
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(parent_id, "root", None, "aiorg_pm_bot")
    subtasks = [
        SubTask(description="A", assigned_dept="aiorg_product_bot"),
        SubTask(description="B", assigned_dept="aiorg_engineering_bot", depends_on=["0"]),
    ]
    task_ids = await orch.dispatch(parent_id, subtasks, chat_id=-123)
    send_fn.reset_mock()
    # A 완료 → B 발송
    await orch.on_task_complete(task_ids[0], "A 완료", chat_id=-123)
    assert send_fn.call_count >= 1
    messages = [call[0][1] for call in send_fn.call_args_list]
    assert any("aiorg_engineering_bot" in msg for msg in messages)


@pytest.mark.asyncio
async def test_all_complete_consolidates(setup):
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(parent_id, "root", None, "aiorg_pm_bot")
    subtasks = [
        SubTask(description="A", assigned_dept="aiorg_product_bot"),
    ]
    task_ids = await orch.dispatch(parent_id, subtasks, chat_id=-123)
    send_fn.reset_mock()
    await orch.on_task_complete(task_ids[0], "기획 완료!", chat_id=-123)
    # Should send consolidation message
    messages = [call[0][1] for call in send_fn.call_args_list]
    assert any("완료" in msg for msg in messages)


@pytest.mark.asyncio
async def test_task_id_namespacing(setup):
    orch, db, send_fn = setup
    tid1 = await orch._next_task_id()
    tid2 = await orch._next_task_id()
    assert tid1.startswith("T-aiorg_pm_bot-")
    assert tid1 != tid2


@pytest.mark.asyncio
async def test_consolidate_results(setup):
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(parent_id, "root", None, "aiorg_pm_bot")
    await db.create_pm_task("T-pm-001", "기획", "aiorg_product_bot", "pm", parent_id=parent_id)
    await db.create_pm_task("T-pm-002", "개발", "aiorg_engineering_bot", "pm", parent_id=parent_id)
    await db.update_pm_task_status("T-pm-001", "done", result="스펙 완성")
    await db.update_pm_task_status("T-pm-002", "done", result="코드 완성")
    summary = await orch.consolidate_results(parent_id)
    assert "기획실" in summary
    assert "개발실" in summary
    assert "스펙 완성" in summary
    assert "코드 완성" in summary


@pytest.mark.asyncio
async def test_detect_relevant_depts_includes_research_when_research_bot_is_registered(setup, monkeypatch):
    class _FakeOrg:
        def __init__(self, org_id, dept_name, role, specialties, direction="", instruction=""):
            self.id = org_id
            self.dept_name = dept_name
            self.role = role
            self.specialties = specialties
            self.direction = direction
            self.instruction = instruction

    class _FakeConfig:
        def list_specialist_orgs(self):
            return [
                _FakeOrg("aiorg_product_bot", "기획실", "기획/요구사항 분석/PRD 작성", ["기획"]),
                _FakeOrg("aiorg_research_bot", "리서치실", "시장조사/레퍼런스 조사/문서 요약/경쟁사 분석", ["시장조사", "레퍼런스조사", "문서요약", "경쟁사분석"]),
                _FakeOrg("aiorg_engineering_bot", "개발실", "개발/코딩/API 구현/버그 수정", ["코딩", "개발"]),
            ]

    monkeypatch.setattr("core.pm_orchestrator.load_orchestration_config", lambda force_reload=False: _FakeConfig())

    orch, db, send_fn = setup
    hints = orch._detect_relevant_depts("최근 코딩에이전트 시장조사와 레퍼런스 조사가 필요해. 리서치 조직을 활용해서 정리해줘")

    assert "aiorg_research_bot" in hints
