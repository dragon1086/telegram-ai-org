"""Tests for discussion_dispatch and _discussion_summarize (US-006)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.pm_orchestrator import PMOrchestrator
from core.result_synthesizer import ResultSynthesizer


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


# ---------------------------------------------------------------------------
# TC1: discussion_dispatch creates parent + 2 subtasks
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discussion_dispatch_creates_parent_and_subtasks() -> None:
    orc = _make_orchestrator()

    call_count = 0

    async def _next_id() -> str:
        nonlocal call_count
        call_count += 1
        return f"T-pm-{call_count:03d}"

    orc._next_task_id = _next_id  # type: ignore[assignment]

    fake_cfg = MagicMock()
    fake_org_a = MagicMock()
    fake_org_a.id = "bot_a"
    fake_org_a.dept_name = "개발실"
    fake_org_b = MagicMock()
    fake_org_b.id = "bot_b"
    fake_org_b.dept_name = "마케팅실"
    fake_cfg.list_orgs.return_value = [fake_org_a, fake_org_b]

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=fake_cfg), \
         patch("core.pm_discussion_mixin.load_orchestration_config", return_value=fake_cfg):
        result = await orc.discussion_dispatch(
            topic="AI 전략 토론",
            dept_hints=["bot_a", "bot_b"],
            chat_id=123,
        )

    assert len(result) == 2, "두 참여자에 대한 서브태스크 ID 반환 기대"

    calls = orc._db.create_pm_task.call_args_list
    assert len(calls) == 3, f"create_pm_task 3회 호출 기대 (부모1 + 서브2), 실제: {len(calls)}"

    # First call = parent task (no parent_id kwarg)
    parent_call_kwargs = calls[0].kwargs
    assert parent_call_kwargs.get("metadata", {}).get("interaction_mode") == "discussion"
    assert "parent_id" not in parent_call_kwargs or parent_call_kwargs.get("parent_id") is None

    # Subtask calls have parent_id set
    parent_task_id = calls[0].kwargs["task_id"]
    for sub_call in calls[1:]:
        assert sub_call.kwargs.get("parent_id") == parent_task_id


# ---------------------------------------------------------------------------
# TC2: insufficient participants → returns [], no DB calls
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discussion_dispatch_insufficient_participants() -> None:
    orc = _make_orchestrator()

    fake_cfg = MagicMock()
    fake_cfg.list_specialist_orgs.return_value = []  # 0 specialist orgs
    fake_cfg.list_orgs.return_value = []

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=fake_cfg), \
         patch("core.pm_discussion_mixin.load_orchestration_config", return_value=fake_cfg):
        result = await orc.discussion_dispatch(
            topic="토론 주제",
            dept_hints=[],  # no dept hints
            chat_id=1,
        )

    assert result == [], "참여자 부족 시 빈 리스트 반환 기대"
    orc._db.create_pm_task.assert_not_called()


# ---------------------------------------------------------------------------
# TC3: _discussion_summarize sends summary and marks parent done
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discussion_summarize_sends_and_marks_done() -> None:
    orc = _make_orchestrator()
    orc._synthesizer = MagicMock()
    orc._synthesizer.summarize_discussion = AsyncMock(return_value="토론 요약 내용")
    orc._synthesize_and_act = AsyncMock()

    results = [{"result": "의견1"}, {"result": "의견2"}]
    await orc._discussion_summarize("parent-123", results, chat_id=456)

    # summarize_discussion called with correct perspectives
    orc._synthesizer.summarize_discussion.assert_called_once_with(["의견1", "의견2"])

    # _send called with "토론 요약" prefix
    orc._send.assert_called_once()
    sent_text = orc._send.call_args[0][1]
    assert "토론 요약" in sent_text

    # update_pm_task_status called with "done"
    orc._db.update_pm_task_status.assert_called_once_with(
        "parent-123", "done", result="토론 요약 내용"
    )


# ---------------------------------------------------------------------------
# TC4: summarize_discussion uses _decision_client with correct prompt
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_summarize_discussion_uses_decision_client() -> None:
    mock_client = MagicMock()
    mock_client.complete = AsyncMock(return_value="중립적 요약 결과")

    synthesizer = ResultSynthesizer(decision_client=mock_client)
    result = await synthesizer.summarize_discussion(["관점1", "관점2"])

    assert result == "중립적 요약 결과"
    mock_client.complete.assert_called_once()
    prompt_used = mock_client.complete.call_args[0][0]
    assert "판단이나 결론 없이" in prompt_used
