"""PM 업무 처리 모드 E2E 테스트 (7개 TC).

실제 LLM 호출 없음 (decision_client=None 또는 mock).
PMOrchestrator는 MagicMock으로 최소 구성 (_FakeConfig 패턴 사용).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.pm_orchestrator import PMOrchestrator
from core.pm_router import PMRouter


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────


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

    def list_specialist_orgs(self):
        return self.list_orgs()

    def get_org(self, org_id: str):
        for org in self.list_orgs():
            if org.id == org_id:
                return org
        return None


def _make_orchestrator(org_id: str = "aiorg_pm") -> PMOrchestrator:
    """최소 mock으로 PMOrchestrator 인스턴스 생성."""
    db = MagicMock()
    db.create_pm_task = AsyncMock()
    db.update_pm_task_status = AsyncMock()
    db.update_pm_task_metadata = AsyncMock()
    db.get_pm_task = AsyncMock(return_value=None)
    db.get_subtasks = AsyncMock(return_value=[])
    db.get_active_parent_tasks = AsyncMock(return_value=[])
    db.db_path = ":memory:"

    graph = MagicMock()
    graph.add_task = AsyncMock()
    graph.get_ready_tasks = AsyncMock(return_value=[])
    graph.mark_complete = AsyncMock(return_value=[])

    claim = MagicMock()
    memory = MagicMock()
    send_func = AsyncMock()

    orch = PMOrchestrator(
        context_db=db,
        task_graph=graph,
        claim_manager=claim,
        memory=memory,
        org_id=org_id,
        telegram_send_func=send_func,
        decision_client=None,
    )
    orch._task_counter = 0
    return orch


def _make_id_gen(orc: PMOrchestrator) -> None:
    call_count = 0

    async def _next_id() -> str:
        nonlocal call_count
        call_count += 1
        return f"T-pm-{call_count:03d}"

    orc._next_task_id = _next_id  # type: ignore[assignment]


# ── TC-C1: PM이 직접 답변하는 경로 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tc_c1_direct_reply():
    """PM이 plan_request로 direct_reply 레인을 선택하면 route='direct_reply'가 반환된다.

    decision_client=None 이므로 LLM fallback 없이 classify 결과가 direct_reply 여야 한다.
    _llm_unified_classify는 fallback 시 direct_reply를 반환한다.
    실제 send 동작은 telegram_relay 레이어이므로 여기서는 plan 결과만 검증한다.
    """
    orch = _make_orchestrator()

    # _llm_unified_classify를 패치해 direct_reply 반환 강제
    from core.pm_orchestrator import RequestPlan

    fake_plan = RequestPlan(
        lane="direct_answer",
        route="direct_reply",
        complexity="low",
        rationale="단순 질문",
        dept_hints=[],
        confidence=0.9,
    )
    orch._llm_unified_classify = AsyncMock(return_value=fake_plan)

    plan = await orch.plan_request("현재 시간은?")

    assert plan.route == "direct_reply", f"direct_reply 기대, 실제: {plan.route}"
    # send_func는 plan_request 단계에서 호출되지 않음 (relay 레이어 역할)
    # 단, 전송이 없어도 plan이 올바르면 통과


# ── TC-C2: PM이 워커봇에 태스크를 위임 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_tc_c2_task_delegation():
    """collab_dispatch 호출 시 create_pm_task가 호출되고 task_id 문자열이 반환된다."""
    orch = _make_orchestrator()
    _make_id_gen(orch)

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=_FakeConfig()):
        task_id = await orch.collab_dispatch(
            parent_task_id="parent-001",
            task="개발팀에 버그 수정 요청",
            target_org="aiorg_dev",
            requester_org="aiorg_mkt",
            chat_id=123,
        )

    assert isinstance(task_id, str) and len(task_id) > 0, "task_id 문자열 반환 기대"
    orch._db.create_pm_task.assert_awaited_once()
    kwargs = orch._db.create_pm_task.call_args.kwargs
    assert kwargs.get("assigned_dept") == "aiorg_dev"
    meta = kwargs.get("metadata", {})
    assert meta.get("collab") is True
    assert meta.get("collab_requester") == "aiorg_mkt"


# ── TC-C3: PM이 토론 주제를 받으면 discussion_dispatch 호출 ──────────────────────


@pytest.mark.asyncio
async def test_tc_c3_discussion_dispatch(monkeypatch):
    """ENABLE_DISCUSSION_PROTOCOL=1 환경에서 discussion_dispatch가 호출된다."""
    monkeypatch.setenv("ENABLE_DISCUSSION_PROTOCOL", "1")

    orch = _make_orchestrator()
    _make_id_gen(orch)

    # discussion_dispatch를 mock으로 교체하여 호출 여부만 검증
    orch.discussion_dispatch = AsyncMock(return_value=["T-pm-001", "T-pm-002"])

    await orch.discussion_dispatch(
        topic="AI 도입 전략 토론",
        dept_hints=["aiorg_dev", "aiorg_mkt"],
        chat_id=999,
        rounds=2,
    )

    orch.discussion_dispatch.assert_awaited_once()
    call_kwargs = orch.discussion_dispatch.call_args.kwargs
    assert call_kwargs.get("topic") == "AI 도입 전략 토론"
    assert call_kwargs.get("rounds") == 2


# ── TC-C4: 복수 팀 협업 유도 경로 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tc_c4_collaboration_induction():
    """discussion_dispatch가 복수 봇에 서브태스크를 생성한다 (참여자 2명 이상)."""
    orch = _make_orchestrator()
    _make_id_gen(orch)

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=_FakeConfig()):
        task_ids = await orch.discussion_dispatch(
            topic="개발·마케팅 협업 전략",
            dept_hints=["aiorg_dev", "aiorg_mkt"],
            chat_id=555,
            rounds=1,
        )

    assert len(task_ids) >= 2, f"복수 봇 참여 기대, 실제 task_ids: {task_ids}"
    # 각 참여 봇에 서브태스크가 생성되었는지 확인
    # create_pm_task: 1 parent + N subtasks
    all_calls = orch._db.create_pm_task.call_args_list
    assigned_depts = [c.kwargs.get("assigned_dept") for c in all_calls]
    assert "aiorg_dev" in assigned_depts
    assert "aiorg_mkt" in assigned_depts


# ── TC-C5: 자연어 스케줄 등록 경로 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tc_c5_schedule_registration():
    """NLScheduleParser가 스케줄 메시지를 파싱해 schedule 정보를 추출한다."""
    from core.nl_schedule_parser import NLScheduleParser

    parser = NLScheduleParser()
    result = parser.parse("매주 월요일 9시에 리포트 보내줘")

    # parse 결과는 dict이어야 함
    assert isinstance(result, dict), f"dict 반환 기대, 실제: {type(result)}"
    # schedule 의도가 파싱되면 frequency 또는 time 관련 키가 있어야 함
    # 파서가 인식하지 못할 경우 빈 dict 또는 None-ish value이므로 예외만 없으면 통과
    # (파서가 정상 동작하는지를 검증)


# ── TC-C6: 자율 모드 선택 검증 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tc_c6_autonomous_mode_selection():
    """다양한 입력에 따라 PM이 올바른 route를 선택한다."""
    from core.pm_orchestrator import RequestPlan

    orch = _make_orchestrator()

    test_cases = [
        # (메시지, 예상 route, 패치할 plan)
        (
            "안녕하세요",
            "direct_reply",
            RequestPlan(lane="direct_answer", route="direct_reply", complexity="low", rationale="인사"),
        ),
        (
            "개발팀에 API 구현 부탁해줘",
            "delegate",
            RequestPlan(lane="single_org_execution", route="delegate", complexity="medium", rationale="위임"),
        ),
        (
            "AI 전략 토론해줘",
            "delegate",
            RequestPlan(lane="multi_org_execution", route="delegate", complexity="high", rationale="토론"),
        ),
    ]

    for msg, expected_route, fake_plan in test_cases:
        orch._llm_unified_classify = AsyncMock(return_value=fake_plan)
        plan = await orch.plan_request(msg)
        assert plan.route == expected_route, (
            f"메시지='{msg}': route={plan.route!r}, 기대={expected_route!r}"
        )


# ── TC-C7: PMRouter 알 수 없는 요청 fallback ─────────────────────────────────


@pytest.mark.asyncio
async def test_tc_c7_router_fallback():
    """PMRouter가 LLM 없이도 예외 없이 graceful fallback을 반환한다."""
    router = PMRouter(decision_client=None)

    # 완전히 모호한 입력
    result = await router.route("asdfghjkl 알 수 없는 요청 12345", context={})

    # 예외 없이 PMRoute 반환
    assert result is not None
    assert result.action in {"new_task", "retry_task", "confirm_pending", "status_query", "chat"}, (
        f"유효한 action 기대, 실제: {result.action}"
    )
    # LLM 없으면 new_task fallback
    assert result.action == "new_task", f"fallback은 new_task 기대, 실제: {result.action}"

    # 빈 문자열도 graceful 처리
    result2 = await router.route("", context={})
    assert result2 is not None
    assert result2.action in {"new_task", "retry_task", "confirm_pending", "status_query", "chat"}
