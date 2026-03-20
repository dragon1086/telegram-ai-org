"""Tests for discussion multi-round ping-pong + persona context injection (Cycle 6)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.pm_orchestrator import PMOrchestrator
from core.agent_persona_memory import AgentStats


def _make_orchestrator() -> PMOrchestrator:
    """Build a minimal PMOrchestrator with all mocked dependencies."""
    db = MagicMock()
    db.create_pm_task = AsyncMock()
    db.update_pm_task_status = AsyncMock()
    db.update_pm_task_metadata = AsyncMock()
    db.get_pm_task = AsyncMock(return_value=None)
    db.get_subtasks = AsyncMock(return_value=[])
    db.db_path = ":memory:"

    task_graph = MagicMock()
    task_graph.add_task = AsyncMock()
    task_graph.get_ready_tasks = AsyncMock(return_value=[])
    claim_manager = MagicMock()
    memory = MagicMock()
    send_func = AsyncMock()

    orc = PMOrchestrator(
        context_db=db,
        task_graph=task_graph,
        claim_manager=claim_manager,
        memory=memory,
        org_id="aiorg_pm",
        telegram_send_func=send_func,
    )
    orc._task_counter = 0
    return orc


def _make_id_gen(orc: PMOrchestrator) -> None:
    call_count = 0

    async def _next_id() -> str:
        nonlocal call_count
        call_count += 1
        return f"T-pm-{call_count:03d}"

    orc._next_task_id = _next_id  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# TC1: discussion_dispatch stores round metadata in parent task
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discussion_dispatch_stores_round_metadata() -> None:
    orc = _make_orchestrator()
    _make_id_gen(orc)

    fake_cfg = MagicMock()
    fake_org_a = MagicMock()
    fake_org_a.id = "bot_a"
    fake_org_a.dept_name = "개발실"
    fake_org_b = MagicMock()
    fake_org_b.id = "bot_b"
    fake_org_b.dept_name = "마케팅실"
    fake_cfg.list_orgs.return_value = [fake_org_a, fake_org_b]

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=fake_cfg):
        await orc.discussion_dispatch(
            topic="AI 전략 토론",
            dept_hints=["bot_a", "bot_b"],
            chat_id=123,
            rounds=2,
        )

    calls = orc._db.create_pm_task.call_args_list
    parent_meta = calls[0].kwargs.get("metadata", {})
    assert parent_meta.get("discussion_rounds") == 2, "discussion_rounds=2 기대"
    assert parent_meta.get("discussion_current_round") == 1, "discussion_current_round=1 기대"
    assert parent_meta.get("discussion_participants") == ["bot_a", "bot_b"], (
        "discussion_participants 저장 기대"
    )


# ---------------------------------------------------------------------------
# TC2: _discussion_summarize triggers next round when current < max
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discussion_summarize_triggers_next_round() -> None:
    orc = _make_orchestrator()
    _make_id_gen(orc)

    # Parent task has round 1 of 2
    orc._db.get_pm_task = AsyncMock(return_value={
        "task_id": "T-pm-001",
        "description": "AI 전략 토론",
        "metadata": {
            "interaction_mode": "discussion",
            "discussion_topic": "AI 전략 토론",
            "discussion_rounds": 2,
            "discussion_current_round": 1,
            "discussion_participants": ["bot_a", "bot_b"],
        },
    })

    # Mock synthesizer
    orc._synthesizer = MagicMock()
    orc._synthesizer.summarize_discussion = AsyncMock(return_value="1라운드 요약")

    results = [
        {"result": "bot_a 의견", "assigned_dept": "bot_a"},
        {"result": "bot_b 의견", "assigned_dept": "bot_b"},
    ]

    fake_cfg = MagicMock()
    fake_org_a = MagicMock()
    fake_org_a.id = "bot_a"
    fake_org_a.dept_name = "개발실"
    fake_org_b = MagicMock()
    fake_org_b.id = "bot_b"
    fake_org_b.dept_name = "마케팅실"
    fake_cfg.list_orgs.return_value = [fake_org_a, fake_org_b]

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=fake_cfg):
        await orc._discussion_summarize("T-pm-001", results, 999)

    # Should NOT mark done — only 'assigned' calls for new subtasks are expected
    done_calls = [
        c for c in orc._db.update_pm_task_status.call_args_list
        if len(c.args) >= 2 and c.args[1] == "done"
    ]
    assert not done_calls, f"done 호출 없어야 함, 실제: {done_calls}"

    # Should update current_round to 2
    orc._db.update_pm_task_metadata.assert_called_once_with(
        "T-pm-001", {"discussion_current_round": 2}
    )

    # Should create 2 new subtasks for round 2
    new_task_calls = orc._db.create_pm_task.call_args_list
    assert len(new_task_calls) == 2, f"라운드 2 서브태스크 2개 기대, 실제: {len(new_task_calls)}"

    # Round summary should be sent
    send_calls = orc._send.call_args_list
    assert any("라운드 1 요약" in str(c) for c in send_calls), "라운드 1 요약 메시지 기대"


# ---------------------------------------------------------------------------
# TC3: _discussion_summarize does final summary when current >= max
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discussion_summarize_final_round() -> None:
    orc = _make_orchestrator()
    _make_id_gen(orc)

    # Parent task: round 2 of 2 (final)
    orc._db.get_pm_task = AsyncMock(return_value={
        "task_id": "T-pm-001",
        "description": "AI 전략 토론",
        "metadata": {
            "interaction_mode": "discussion",
            "discussion_topic": "AI 전략 토론",
            "discussion_rounds": 2,
            "discussion_current_round": 2,
            "discussion_participants": ["bot_a", "bot_b"],
        },
    })

    orc._synthesizer = MagicMock()
    orc._synthesizer.summarize_discussion = AsyncMock(return_value="최종 토론 요약")
    orc._synthesize_and_act = AsyncMock()

    results = [
        {"result": "bot_a 2라운드 의견", "assigned_dept": "bot_a"},
        {"result": "bot_b 2라운드 의견", "assigned_dept": "bot_b"},
    ]

    await orc._discussion_summarize("T-pm-001", results, 999)

    # Should mark done
    orc._db.update_pm_task_status.assert_called_once_with(
        "T-pm-001", "done", result="최종 토론 요약"
    )

    # Should NOT create new subtasks
    orc._db.create_pm_task.assert_not_called()

    # Should send final summary with '토론 요약'
    send_calls = orc._send.call_args_list
    assert any("토론 요약" in str(c) for c in send_calls), "'토론 요약' 메시지 기대"


# ---------------------------------------------------------------------------
# TC4: persona context injected into structured prompt when apm has stats
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_persona_context_injected() -> None:
    orc = _make_orchestrator()
    _make_id_gen(orc)

    # Setup fake apm with stats
    fake_apm = MagicMock()
    fake_stats = AgentStats(
        agent_id="aiorg_engineering_bot",
        strengths=["coding", "ops"],
        weaknesses=["design"],
    )
    fake_apm.get_stats = MagicMock(return_value=fake_stats)
    orc._apm = fake_apm

    # Capture the context passed to _prompt_gen.generate
    captured_contexts: list[str] = []

    async def _fake_generate(description: str, dept: str, context: str = "") -> MagicMock:
        captured_contexts.append(context)
        sp = MagicMock()
        sp.render.return_value = description
        return sp

    orc._prompt_gen.generate = _fake_generate  # type: ignore[assignment]
    orc._db.create_pm_task = AsyncMock()
    orc._db.update_pm_task_status = AsyncMock()

    from core.pm_orchestrator import SubTask

    subtasks = [SubTask(description="API 구현", assigned_dept="aiorg_engineering_bot")]

    # Minimal parent_metadata & task_packet helpers
    orc._build_subtask_packet = MagicMock(return_value={  # type: ignore[assignment]
        "original_request": "서비스 개발",
        "goal": "API 구현",
        "user_expectations": [],
    })
    orc._db.get_pm_task = AsyncMock(return_value={
        "task_id": "T-pm-001",
        "metadata": {},
    })

    await orc.dispatch("T-pm-001", subtasks, 999)

    assert len(captured_contexts) == 1, "generate가 한 번 호출되어야 함"
    ctx = captured_contexts[0]
    assert "coding" in ctx or "ops" in ctx, f"강점이 context에 포함되어야 함. 실제: {ctx!r}"
    assert "design" in ctx, f"약점이 context에 포함되어야 함. 실제: {ctx!r}"


# ---------------------------------------------------------------------------
# TC5: on_task_complete triggers _synthesize_and_act only when all round-1 tasks done
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_on_task_complete_round_filtering() -> None:
    orc = _make_orchestrator()
    _make_id_gen(orc)

    # Sibling subtasks: both round 1
    sibling_a = {
        "id": "T-pm-001", "status": "done",
        "description": "의견 제시",
        "assigned_dept": "bot_a",
        "metadata": {"interaction_mode": "discussion", "discussion_round": 1},
        "parent_id": "T-pm-000",
    }
    sibling_b = {
        "id": "T-pm-002", "status": "assigned",  # not yet done
        "description": "의견 제시",
        "assigned_dept": "bot_b",
        "metadata": {"interaction_mode": "discussion", "discussion_round": 1},
        "parent_id": "T-pm-000",
    }

    orc._db.get_pm_task = AsyncMock(return_value={
        "id": "T-pm-001",
        "task_id": "T-pm-001",
        "parent_id": "T-pm-000",
        "metadata": {"interaction_mode": "discussion", "discussion_round": 1},
    })
    orc._db.get_subtasks = AsyncMock(return_value=[sibling_a, sibling_b])

    synthesize_called = False

    async def _fake_synthesize(parent_id, subtasks, chat_id, **kwargs):
        nonlocal synthesize_called
        synthesize_called = True

    orc._synthesize_and_act = _fake_synthesize  # type: ignore[assignment]
    orc._graph.mark_complete = AsyncMock(return_value=[])

    await orc.on_task_complete("T-pm-001", result="의견A", chat_id=999)

    assert not synthesize_called, "sibling_b가 아직 미완료 — _synthesize_and_act 미호출 기대"

    # Now mark sibling_b done
    sibling_b["status"] = "done"
    orc._db.get_pm_task = AsyncMock(return_value={
        "id": "T-pm-002",
        "task_id": "T-pm-002",
        "parent_id": "T-pm-000",
        "metadata": {"interaction_mode": "discussion", "discussion_round": 1},
    })
    orc._db.get_subtasks = AsyncMock(return_value=[sibling_a, sibling_b])
    orc._graph.mark_complete = AsyncMock(return_value=[])

    await orc.on_task_complete("T-pm-002", result="의견B", chat_id=999)

    assert synthesize_called, "모든 라운드 1 서브태스크 완료 → _synthesize_and_act 호출 기대"


# ---------------------------------------------------------------------------
# TC6: _discussion_summarize early-terminates on consensus (no conflict)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discussion_early_termination_on_consensus() -> None:
    orc = _make_orchestrator()
    _make_id_gen(orc)

    orc._db.get_pm_task = AsyncMock(return_value={
        "task_id": "T-pm-001",
        "metadata": {
            "interaction_mode": "discussion",
            "discussion_topic": "AI 방향성",
            "discussion_rounds": 3,
            "discussion_current_round": 1,
            "discussion_participants": ["bot_a", "bot_b"],
        },
    })

    orc._synthesizer = MagicMock()
    orc._synthesizer.summarize_discussion = AsyncMock(return_value="1라운드 요약")

    # No conflict, has consensus
    orc._detect_discussion_conflict = AsyncMock(return_value=(False, ""))
    orc._detect_discussion_consensus = AsyncMock(return_value=True)

    results = [
        {"result": "동의합니다", "assigned_dept": "bot_a",
         "metadata": {"discussion_round": 1}},
        {"result": "맞습니다", "assigned_dept": "bot_b",
         "metadata": {"discussion_round": 1}},
    ]

    await orc._discussion_summarize("T-pm-001", results, chat_id=999)

    # Should mark done (early termination)
    done_calls = [
        c for c in orc._db.update_pm_task_status.call_args_list
        if len(c.args) >= 2 and c.args[1] == "done"
    ]
    assert done_calls, "합의 도달 시 parent done 기대"

    # Should NOT create new subtasks
    orc._db.create_pm_task.assert_not_called()

    # Send message should mention 합의
    send_texts = [str(c) for c in orc._send.call_args_list]
    assert any("합의" in t for t in send_texts), "합의 메시지 전송 기대"


# ---------------------------------------------------------------------------
# TC7: conflict enriches follow-up question
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discussion_conflict_enriches_followup() -> None:
    orc = _make_orchestrator()

    # No LLM — use fallback
    orc._decision_client = None

    followup = await orc._generate_discussion_followup(
        topic="AI 전략",
        round_summary="라운드 요약",
        next_round=2,
        has_conflict=True,
        conflict_points="비용 대비 효율 문제",
    )

    assert "충돌 포인트" in followup or "비용 대비 효율" in followup, (
        f"conflict_points가 follow-up에 포함되어야 함. 실제: {followup!r}"
    )


# ---------------------------------------------------------------------------
# TC8: no conflict + no consensus → next round proceeds
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discussion_indeterminate_continues() -> None:
    orc = _make_orchestrator()
    _make_id_gen(orc)

    orc._db.get_pm_task = AsyncMock(return_value={
        "task_id": "T-pm-001",
        "metadata": {
            "interaction_mode": "discussion",
            "discussion_topic": "미래 전략",
            "discussion_rounds": 3,
            "discussion_current_round": 1,
            "discussion_participants": ["bot_a", "bot_b"],
        },
    })

    orc._synthesizer = MagicMock()
    orc._synthesizer.summarize_discussion = AsyncMock(return_value="1라운드 요약")

    # No conflict, no consensus
    orc._detect_discussion_conflict = AsyncMock(return_value=(False, ""))
    orc._detect_discussion_consensus = AsyncMock(return_value=False)

    results = [
        {"result": "의견A", "assigned_dept": "bot_a",
         "metadata": {"discussion_round": 1}},
        {"result": "의견B", "assigned_dept": "bot_b",
         "metadata": {"discussion_round": 1}},
    ]

    fake_cfg = MagicMock()
    fake_org_a = MagicMock()
    fake_org_a.id = "bot_a"
    fake_org_a.dept_name = "개발실"
    fake_org_b = MagicMock()
    fake_org_b.id = "bot_b"
    fake_org_b.dept_name = "마케팅실"
    fake_cfg.list_orgs.return_value = [fake_org_a, fake_org_b]

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=fake_cfg):
        await orc._discussion_summarize("T-pm-001", results, chat_id=999)

    # Should NOT mark done
    done_calls = [
        c for c in orc._db.update_pm_task_status.call_args_list
        if len(c.args) >= 2 and c.args[1] == "done"
    ]
    assert not done_calls, "indeterminate 시 done 호출 없어야 함"

    # Should update round to 2
    orc._db.update_pm_task_metadata.assert_called_once_with(
        "T-pm-001", {"discussion_current_round": 2}
    )

    # Should create 2 new subtasks for round 2
    new_task_calls = orc._db.create_pm_task.call_args_list
    assert len(new_task_calls) == 2, f"라운드 2 서브태스크 2개 기대, 실제: {len(new_task_calls)}"
