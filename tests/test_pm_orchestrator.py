"""PMOrchestrator 단위 테스트."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.claim_manager import ClaimManager
from core.context_db import ContextDB
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator, SubTask
from core.task_graph import TaskGraph


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
    monkeypatch.setattr("core.pm_orchestrator.KNOWN_DEPTS", {})
    orch, db, send_fn = setup

    plan = await orch.plan_request("기획하고 디자인하고 개발해줘")

    assert plan.route == "local_execution"


@pytest.mark.asyncio
async def test_decompose_returns_empty_without_specialists(setup, monkeypatch):
    class _EmptyConfig:
        def list_specialist_orgs(self):
            return []

    monkeypatch.setattr("core.pm_orchestrator.load_orchestration_config", lambda force_reload=False: _EmptyConfig())
    monkeypatch.setattr("core.pm_orchestrator.KNOWN_DEPTS", {})
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


@pytest.mark.asyncio
async def test_improve_status_handler_exists(setup):
    orch, db, send_fn = setup
    assert hasattr(orch, "_handle_improve_status"), "PMOrchestrator에 _handle_improve_status 메서드가 없다"
    result = await orch._handle_improve_status(chat_id=12345)
    assert isinstance(result, str)
    assert len(result) > 0
    send_fn.assert_called()


@pytest.mark.asyncio
async def test_dispatch_deps_registered_before_task_created(setup):
    """레이스 컨디션 수정(cf42da4) 검증: 의존성 등록이 태스크 본문 생성보다 먼저 완료되는지 확인.

    pm_orchestrator._dispatch_subtasks 에서 Step 0(ID 사전 생성 + deps 등록)이
    Step 1(태스크 본문 DB 삽입) 보다 먼저 실행되어야 한다.
    TaskPoller가 2초 주기로 polling 할 때 의존성이 이미 등록되어 있어야
    후행 태스크를 조기 수신하지 않는다.
    """
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(parent_id, "root", None, "aiorg_pm_bot")

    call_order: list[str] = []
    original_add_dep = db.add_dependency
    original_create_task = db.create_pm_task

    async def recording_add_dep(task_id: str, depends_on: str):
        call_order.append(f"add_dep:{task_id}")
        return await original_add_dep(task_id, depends_on)

    async def recording_create_task(task_id, description, assigned_dept, created_by, **kwargs):
        call_order.append(f"create_task:{task_id}")
        return await original_create_task(
            task_id, description, assigned_dept, created_by, **kwargs
        )

    db.add_dependency = recording_add_dep
    db.create_pm_task = recording_create_task

    subtasks = [
        SubTask(description="리서치", assigned_dept="aiorg_research_bot"),
        SubTask(description="개발", assigned_dept="aiorg_engineering_bot", depends_on=["0"]),
        SubTask(description="운영", assigned_dept="aiorg_ops_bot", depends_on=["1"]),
    ]
    await orch.dispatch(parent_id, subtasks, chat_id=-123)

    # add_dep 이벤트들이 create_task 이벤트들보다 먼저 나타나야 한다
    dep_indices = [i for i, ev in enumerate(call_order) if ev.startswith("add_dep:")]
    create_indices = [i for i, ev in enumerate(call_order) if ev.startswith("create_task:") and ev != f"create_task:{parent_id}"]

    assert dep_indices, "add_dependency 호출이 없음 — deps 미등록 상태"
    assert create_indices, "create_pm_task(서브태스크) 호출이 없음"
    # 최초 dep 등록이 최초 서브태스크 create 보다 먼저여야 한다
    assert min(dep_indices) < min(create_indices), (
        f"deps 등록({min(dep_indices)})이 태스크 생성({min(create_indices)})보다 늦음 — 레이스 컨디션 재발"
    )


@pytest.mark.asyncio
async def test_dispatch_sequential_research_eng_ops(setup):
    """리서치→개발실→운영실 순서 검증: 첫 웨이브에 리서치만, 리서치 완료 후 개발실만, 개발 완료 후 운영실."""
    orch, db, send_fn = setup
    parent_id = "T-pm-root"
    await db.create_pm_task(parent_id, "root", None, "aiorg_pm_bot")

    subtasks = [
        SubTask(description="시장조사", assigned_dept="aiorg_research_bot"),
        SubTask(description="코드구현", assigned_dept="aiorg_engineering_bot", depends_on=["0"]),
        SubTask(description="배포", assigned_dept="aiorg_ops_bot", depends_on=["1"]),
    ]
    task_ids = await orch.dispatch(parent_id, subtasks, chat_id=-123)
    research_id, eng_id, ops_id = task_ids[0], task_ids[1], task_ids[2]

    # 첫 웨이브: 리서치만 발송
    first_wave_msgs = [call[0][1] for call in send_fn.call_args_list]
    assert any("aiorg_research_bot" in m for m in first_wave_msgs), "첫 웨이브에 리서치가 없음"
    assert not any(f"[PM_TASK:{eng_id}]" in m for m in first_wave_msgs), "개발실이 첫 웨이브에 조기 발송됨"
    assert not any(f"[PM_TASK:{ops_id}]" in m for m in first_wave_msgs), "운영실이 첫 웨이브에 조기 발송됨"

    send_fn.reset_mock()

    # 리서치 완료 → 개발실만 발송
    await orch.on_task_complete(research_id, "리서치 완료", chat_id=-123)
    second_wave_msgs = [call[0][1] for call in send_fn.call_args_list]
    assert any("aiorg_engineering_bot" in m for m in second_wave_msgs), "리서치 완료 후 개발실 미발송"
    assert not any(f"[PM_TASK:{ops_id}]" in m for m in second_wave_msgs), "운영실이 개발 전에 발송됨"

    send_fn.reset_mock()

    # 개발 완료 → 운영실만 발송
    await orch.on_task_complete(eng_id, "개발 완료", chat_id=-123)
    third_wave_msgs = [call[0][1] for call in send_fn.call_args_list]
    assert any("aiorg_ops_bot" in m for m in third_wave_msgs), "개발 완료 후 운영실 미발송"


# ── 팀 구성 가시성 버그(T-669) 수정 검증: 경로 B (다부서 합성 최종 보고) ──────────────────


@pytest.mark.asyncio
async def test_synthesize_and_act_includes_team_header_sufficient(setup, monkeypatch):
    """경로 B(다부서 합성 SUFFICIENT): 최종 보고 메시지에 팀 구성 헤더가 포함되어야 한다."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.result_synthesizer import SynthesisJudgment, SynthesisResult

    orch, db, send_fn = setup

    parent_id = "T-team-header-test"
    await db.create_pm_task(parent_id, "다부서 테스트 요청", None, "aiorg_pm_bot")

    subtasks_data = [
        {
            "task_id": "T-sub-1",
            "description": "리서치",
            "assigned_dept": "aiorg_research_bot",
            "status": "done",
            "result": "리서치 결과입니다.",
            "metadata": {},
        },
        {
            "task_id": "T-sub-2",
            "description": "개발",
            "assigned_dept": "aiorg_engineering_bot",
            "status": "done",
            "result": "개발 결과입니다.",
            "metadata": {},
        },
    ]

    mock_synthesis = SynthesisResult(
        judgment=SynthesisJudgment.SUFFICIENT,
        summary="통합 요약",
        unified_report="최종 보고서 내용입니다.",
    )

    with patch.object(orch._synthesizer, "synthesize", new=AsyncMock(return_value=mock_synthesis)):
        await orch._synthesize_and_act(parent_id, subtasks_data, chat_id=-999)

    all_sent = [call[0][1] for call in send_fn.call_args_list]
    # 최종 보고 메시지(ARTIFACT 마커 포함)
    final_reports = [m for m in all_sent if "최종 보고서 내용입니다." in m or "[ARTIFACT:" in m]
    assert final_reports, "최종 보고 메시지가 전송되지 않음"

    report_msg = final_reports[0]
    # 팀 구성 헤더가 포함되어야 한다
    assert "🏗️" in report_msg or "팀 구성" in report_msg, (
        f"팀 구성 헤더가 보고 메시지에 없음. 실제: {report_msg[:300]}"
    )
    # 두 부서 모두 언급되어야 한다
    assert "aiorg_research_bot" in report_msg or "리서치" in report_msg, (
        "리서치 부서가 팀 헤더에 미포함"
    )
    assert "aiorg_engineering_bot" in report_msg or "개발" in report_msg, (
        "개발 부서가 팀 헤더에 미포함"
    )


@pytest.mark.asyncio
async def test_synthesize_and_act_team_header_absent_when_no_depts(setup, monkeypatch):
    """서브태스크에 assigned_dept가 없으면 팀 헤더가 없어도 오류가 발생하지 않는다."""
    from unittest.mock import AsyncMock, patch

    from core.result_synthesizer import SynthesisJudgment, SynthesisResult

    orch, db, send_fn = setup

    parent_id = "T-no-dept-test"
    await db.create_pm_task(parent_id, "부서 없는 테스트", None, "aiorg_pm_bot")

    subtasks_data = [
        {
            "task_id": "T-sub-nd",
            "description": "작업",
            "assigned_dept": "",
            "status": "done",
            "result": "결과",
            "metadata": {},
        },
    ]

    mock_synthesis = SynthesisResult(
        judgment=SynthesisJudgment.SUFFICIENT,
        summary="요약",
        unified_report="보고서",
    )

    # render_team_header가 빈 리스트로 호출되어도 예외 없이 처리되어야 한다
    with patch.object(orch._synthesizer, "synthesize", new=AsyncMock(return_value=mock_synthesis)):
        await orch._synthesize_and_act(parent_id, subtasks_data, chat_id=-999)

    # 최소한 보고서가 전송됐는지 확인 (팀 헤더 없이도 오류 없음)
    all_sent = [call[0][1] for call in send_fn.call_args_list]
    assert any("보고서" in m for m in all_sent), "보고서가 전송되지 않음"


@pytest.mark.asyncio
async def test_synthesize_and_act_includes_team_header_insufficient(setup, monkeypatch):
    """경로 B INSUFFICIENT: 재작업 알림 메시지에도 팀 구성 헤더가 포함되어야 한다."""
    from unittest.mock import AsyncMock, patch

    from core.result_synthesizer import SynthesisJudgment, SynthesisResult

    orch, db, send_fn = setup

    parent_id = "T-insufficient-header"
    await db.create_pm_task(parent_id, "부족 결과 테스트", None, "aiorg_pm_bot")

    subtasks_data = [
        {
            "task_id": "T-sub-ins",
            "description": "작업",
            "assigned_dept": "aiorg_design_bot",
            "status": "done",
            "result": "미흡한 결과",
            "metadata": {},
        },
    ]

    mock_synthesis = SynthesisResult(
        judgment=SynthesisJudgment.INSUFFICIENT,
        summary="부족 요약",
        unified_report="부족 보고서",
        reasoning="결과가 충분하지 않습니다.",
        follow_up_tasks=[{"dept": "aiorg_design_bot", "description": "보완 작업"}],
    )

    with patch.object(orch._synthesizer, "synthesize", new=AsyncMock(return_value=mock_synthesis)):
        await orch._synthesize_and_act(parent_id, subtasks_data, chat_id=-999)

    all_sent = [call[0][1] for call in send_fn.call_args_list]
    # INSUFFICIENT 알림 메시지 확인
    insufficient_msgs = [m for m in all_sent if "결과 부족" in m or "재작업" in m]
    assert insufficient_msgs, "INSUFFICIENT 알림이 전송되지 않음"

    msg = insufficient_msgs[0]
    assert "🏗️" in msg or "팀 구성" in msg, (
        f"INSUFFICIENT 알림에 팀 구성 헤더가 없음. 실제: {msg[:300]}"
    )


@pytest.mark.asyncio
async def test_synthesize_and_act_includes_team_header_conflicting(setup, monkeypatch):
    """경로 B CONFLICTING: 충돌 알림 메시지에도 팀 구성 헤더가 포함되어야 한다."""
    from unittest.mock import AsyncMock, patch

    from core.result_synthesizer import SynthesisJudgment, SynthesisResult

    orch, db, send_fn = setup

    parent_id = "T-conflicting-header"
    await db.create_pm_task(parent_id, "충돌 결과 테스트", None, "aiorg_pm_bot")

    subtasks_data = [
        {
            "task_id": "T-sub-c1",
            "description": "작업A",
            "assigned_dept": "aiorg_engineering_bot",
            "status": "done",
            "result": "방안 A",
            "metadata": {},
        },
        {
            "task_id": "T-sub-c2",
            "description": "작업B",
            "assigned_dept": "aiorg_design_bot",
            "status": "done",
            "result": "방안 B",
            "metadata": {},
        },
    ]

    mock_synthesis = SynthesisResult(
        judgment=SynthesisJudgment.CONFLICTING,
        summary="충돌 요약",
        unified_report="충돌 보고서 내용",
        reasoning="두 부서가 상충하는 방향을 제시함",
    )

    with patch.object(orch._synthesizer, "synthesize", new=AsyncMock(return_value=mock_synthesis)):
        await orch._synthesize_and_act(parent_id, subtasks_data, chat_id=-999)

    all_sent = [call[0][1] for call in send_fn.call_args_list]
    conflicting_msgs = [m for m in all_sent if "충돌" in m or "CONFLICTING" in m.upper()]
    assert conflicting_msgs, "CONFLICTING 알림이 전송되지 않음"

    msg = conflicting_msgs[0]
    assert "🏗️" in msg or "팀 구성" in msg, (
        f"CONFLICTING 알림에 팀 구성 헤더가 없음. 실제: {msg[:300]}"
    )


@pytest.mark.asyncio
async def test_synthesize_and_act_includes_team_header_needs_integration(setup, monkeypatch):
    """경로 B NEEDS_INTEGRATION: 통합 보고 메시지에도 팀 구성 헤더가 포함되어야 한다."""
    from unittest.mock import AsyncMock, patch

    from core.result_synthesizer import SynthesisJudgment, SynthesisResult

    orch, db, send_fn = setup

    parent_id = "T-needs-integration-header"
    await db.create_pm_task(parent_id, "통합 필요 테스트", None, "aiorg_pm_bot")

    subtasks_data = [
        {
            "task_id": "T-sub-ni1",
            "description": "리서치 파트",
            "assigned_dept": "aiorg_research_bot",
            "status": "done",
            "result": "리서치 결과 A",
            "metadata": {},
        },
        {
            "task_id": "T-sub-ni2",
            "description": "기획 파트",
            "assigned_dept": "aiorg_product_bot",
            "status": "done",
            "result": "기획 결과 B",
            "metadata": {},
        },
    ]

    mock_synthesis = SynthesisResult(
        judgment=SynthesisJudgment.NEEDS_INTEGRATION,
        summary="통합 필요 요약",
        unified_report="통합이 필요한 보고서 내용",
    )

    with patch.object(orch._synthesizer, "synthesize", new=AsyncMock(return_value=mock_synthesis)):
        await orch._synthesize_and_act(parent_id, subtasks_data, chat_id=-999)

    all_sent = [call[0][1] for call in send_fn.call_args_list]
    integration_msgs = [m for m in all_sent if "통합이 필요한 보고서" in m or "[ARTIFACT:" in m]
    assert integration_msgs, "NEEDS_INTEGRATION 보고 메시지가 전송되지 않음"

    msg = integration_msgs[0]
    assert "🏗️" in msg or "팀 구성" in msg, (
        f"NEEDS_INTEGRATION 보고에 팀 구성 헤더가 없음. 실제: {msg[:300]}"
    )
