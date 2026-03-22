"""Phase 4: 멀티턴 대화 시나리오 검증 — 컨텍스트 창 크기 최적화.

검증 항목:
1. 5턴·10턴·20턴에서 PM이 이전 맥락을 올바르게 반영하는지
2. 컨텍스트 크기별(N=5/10/20, 토큰 1000/2000/4000) 토큰 소비량 측정
3. 50턴 이상에서 토큰 한도 초과 방지 로직 정상 동작 확인
4. 하위 호환 (history=None) 검증
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.context_window import (
    MAX_HISTORY_MESSAGES,
    MAX_HISTORY_TOKENS,
    build_context_window,
    estimate_tokens,
    format_history_for_prompt,
)
from core.pm_orchestrator import PMOrchestrator


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_turn(n: int, content_len: int = 40) -> list[dict]:
    """n턴 분량의 대화 이력 생성 (DESC — 최신이 앞).

    홀수 인덱스 = 사용자, 짝수 인덱스 = 봇 응답.
    """
    msgs = []
    for i in range(n - 1, -1, -1):
        is_bot = i % 2 == 0
        msgs.append({
            "content": f"{'봇' if is_bot else '사용자'} 메시지 {i}: " + ("x" * content_len),
            "role": "bot" if is_bot else "user",
            "is_bot": is_bot,
            "timestamp": f"2026-01-01T{(i // 60):02d}:{(i % 60):02d}:00",
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


# ── 1. 멀티턴 컨텍스트 보존 ──────────────────────────────────────────────────

class TestMultiTurnContextPreservation:
    """5·10·20턴에서 PM 프롬프트에 이전 맥락이 포함되는지 검증."""

    @pytest.mark.parametrize("n_turns", [5, 10, 20])
    def test_context_appears_in_decompose_prompt(self, n_turns: int):
        orch = _make_orchestrator()
        history = _make_turn(n_turns)
        prompt = orch._build_decompose_prompt(
            "PM 봇 개선해줘", [], conversation_history=history
        )
        assert "[CONTEXT]" in prompt
        assert "[/CONTEXT]" in prompt
        # 적어도 1개 이상 메시지가 포함돼야 함
        assert "사용자" in prompt or "봇" in prompt

    @pytest.mark.parametrize("n_turns", [5, 10, 20])
    def test_context_window_not_exceed_defaults(self, n_turns: int):
        history = _make_turn(n_turns)
        result = build_context_window(
            history,
            max_messages=MAX_HISTORY_MESSAGES,
            max_tokens=MAX_HISTORY_TOKENS,
        )
        # 메시지 수 한도
        assert len(result) <= MAX_HISTORY_MESSAGES
        # 토큰 합산 한도
        total = sum(estimate_tokens(str(m.get("content", ""))) for m in result)
        assert total <= MAX_HISTORY_TOKENS

    def test_context_chronological_in_prompt(self):
        """프롬프트 내 맥락이 시간 오름차순이어야 함."""
        history = _make_turn(8)
        result = build_context_window(history, max_messages=10, max_tokens=5000)
        timestamps = [m["timestamp"] for m in result]
        assert timestamps == sorted(timestamps)


# ── 2. 컨텍스트 크기별 토큰 소비량 측정 ──────────────────────────────────────

class TestContextSizeBenchmark:
    """N=5/10/20, 토큰 1000/2000/4000 조합별 포함 메시지 수와 토큰 소비량."""

    @pytest.mark.parametrize("max_msgs,max_tok", [
        (5, 1000),
        (10, 2000),
        (20, 4000),
    ])
    def test_token_consumption_within_budget(self, max_msgs: int, max_tok: int):
        # 각 메시지 ~60자 → ~15 tokens
        history = _make_turn(30, content_len=60)
        result = build_context_window(history, max_messages=max_msgs, max_tokens=max_tok)
        total_tokens = sum(estimate_tokens(str(m.get("content", ""))) for m in result)
        assert len(result) <= max_msgs
        assert total_tokens <= max_tok

    @pytest.mark.parametrize("max_msgs,max_tok", [
        (5, 1000),
        (10, 2000),
        (20, 4000),
    ])
    def test_format_output_valid_for_all_budgets(self, max_msgs: int, max_tok: int):
        history = _make_turn(30, content_len=60)
        result = format_history_for_prompt(
            history, max_messages=max_msgs, max_tokens=max_tok
        )
        # 빈 문자열이거나 올바른 태그 형식이어야 함
        if result:
            assert result.startswith("[CONTEXT]")
            assert result.strip().endswith("[/CONTEXT]")

    def test_larger_budget_includes_more_messages(self):
        """예산이 클수록 더 많은 메시지가 포함된다."""
        history = _make_turn(25, content_len=40)
        small = build_context_window(history, max_messages=5, max_tokens=500)
        large = build_context_window(history, max_messages=20, max_tokens=4000)
        assert len(large) >= len(small)


# ── 3. 50턴+ 엣지 케이스 — 토큰 한도 초과 방지 ──────────────────────────────

class TestLongHistoryEdgeCases:
    """50턴 이상 대화에서 토큰 한도 초과 방지 로직 검증."""

    def test_50_turns_token_guard(self):
        history = _make_turn(50)
        result = build_context_window(history, max_messages=10, max_tokens=2000)
        total = sum(estimate_tokens(str(m.get("content", ""))) for m in result)
        assert len(result) <= 10
        assert total <= 2000

    def test_100_turns_no_crash(self):
        """100턴에서도 crash 없이 처리."""
        history = _make_turn(100, content_len=200)
        result = build_context_window(history, max_messages=10, max_tokens=2000)
        assert isinstance(result, list)
        assert len(result) <= 10

    def test_very_long_messages_truncated_in_format(self):
        """단일 메시지가 매우 길면 300자에서 잘려야 함."""
        history = [
            {
                "content": "A" * 1000,
                "role": "user",
                "is_bot": False,
                "timestamp": "2026-01-01T10:00:00",
            }
        ]
        result = format_history_for_prompt(history, max_messages=5, max_tokens=5000)
        assert "A" * 301 not in result
        assert "A" * 300 in result

    def test_token_limit_zero_returns_empty(self):
        history = _make_turn(10, content_len=400)
        result = build_context_window(history, max_messages=10, max_tokens=5)
        assert result == []

    def test_format_empty_when_all_tokens_exceeded(self):
        history = _make_turn(10, content_len=400)
        result = format_history_for_prompt(history, max_messages=10, max_tokens=5)
        assert result == ""


# ── 4. 하위 호환성 — history=None / 빈 리스트 ─────────────────────────────────

class TestBackwardCompatibility:
    """기존 단일 메시지 방식과 하위 호환성 검증."""

    def test_build_context_window_empty_list(self):
        assert build_context_window([]) == []

    def test_format_history_empty_list_returns_empty_string(self):
        assert format_history_for_prompt([]) == ""

    def test_decompose_prompt_no_history(self):
        orch = _make_orchestrator()
        prompt = orch._build_decompose_prompt("PM 봇 개선", [], conversation_history=None)
        assert "PM 봇 개선" in prompt
        assert "[CONTEXT]" not in prompt

    def test_decompose_prompt_empty_history(self):
        orch = _make_orchestrator()
        prompt = orch._build_decompose_prompt("PM 봇 개선", [], conversation_history=[])
        assert "PM 봇 개선" in prompt
        assert "[CONTEXT]" not in prompt

    @pytest.mark.asyncio
    async def test_plan_request_no_history_compat(self):
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(
            return_value='{"lane":"single_org_execution","route":"delegate","complexity":"medium","rationale":"테스트"}'
        )
        orch = _make_orchestrator(decision_client=mock_client)
        with patch.object(orch, "_detect_relevant_depts", return_value=[]):
            with patch.object(orch, "_extract_workdir", return_value=None):
                plan = await orch.plan_request("새 기능 개발해줘")
        assert plan is not None

    @pytest.mark.asyncio
    async def test_plan_request_with_context_injects_block(self):
        captured: list[str] = []

        async def _complete(prompt: str, **kwargs) -> str:
            captured.append(prompt)
            return '{"lane":"single_org_execution","route":"delegate","complexity":"medium","rationale":"테스트"}'

        mock_client = MagicMock()
        mock_client.complete = _complete
        orch = _make_orchestrator(decision_client=mock_client)
        history = _make_turn(5)
        with patch.object(orch, "_detect_relevant_depts", return_value=[]):
            with patch.object(orch, "_extract_workdir", return_value=None):
                await orch.plan_request("새 기능 개발해줘", conversation_history=history)
        assert len(captured) >= 1
        assert "[CONTEXT]" in captured[0]


# ── 5. 기본값 검증 ────────────────────────────────────────────────────────────

def test_default_max_history_messages_reasonable():
    assert 5 <= MAX_HISTORY_MESSAGES <= 30


def test_default_max_history_tokens_reasonable():
    assert 500 <= MAX_HISTORY_TOKENS <= 8000
