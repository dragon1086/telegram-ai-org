"""Tests for PMJudgmentGate."""
from __future__ import annotations
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pm_judgment_gate import PMJudgmentGate, JudgmentVerdict, JudgmentResult


class TestEvaluateSync:
    def test_empty_result_returns_reject(self):
        gate = PMJudgmentGate()
        result = gate.evaluate_sync("태스크", "")
        assert result.verdict == JudgmentVerdict.REJECT
        assert result.rework_prompt != ""

    def test_short_result_returns_reject(self):
        gate = PMJudgmentGate()
        result = gate.evaluate_sync("태스크", "짧음")
        assert result.verdict == JudgmentVerdict.REJECT

    def test_sufficient_result_returns_approve(self):
        gate = PMJudgmentGate()
        long_result = "이것은 충분히 긴 결과입니다. " * 5
        result = gate.evaluate_sync("태스크", long_result)
        assert result.verdict == JudgmentVerdict.APPROVE

    def test_error_pattern_returns_reject(self):
        gate = PMJudgmentGate()
        result = gate.evaluate_sync("태스크", "Error: 실패했습니다")
        assert result.verdict == JudgmentVerdict.REJECT

    def test_judgment_result_dataclass(self):
        jr = JudgmentResult(verdict=JudgmentVerdict.APPROVE, reasoning="OK")
        assert jr.suggested_dept == ""
        assert jr.rework_prompt == ""

    def test_verdict_values(self):
        assert JudgmentVerdict.APPROVE == "approve"
        assert JudgmentVerdict.REROUTE == "reroute"
        assert JudgmentVerdict.REJECT == "reject"


class TestEvaluateAsync:
    @pytest.mark.asyncio
    async def test_no_decision_client_uses_heuristic(self):
        gate = PMJudgmentGate()
        result = await gate.evaluate("태스크", "충분한 결과입니다. " * 3)
        assert result.verdict == JudgmentVerdict.APPROVE

    @pytest.mark.asyncio
    async def test_short_result_async_reject(self):
        gate = PMJudgmentGate()
        result = await gate.evaluate("태스크", "짧음", decision_client=None)
        assert result.verdict == JudgmentVerdict.REJECT

    @pytest.mark.asyncio
    async def test_decision_client_failure_fallback(self):
        class FailingClient:
            async def ask(self, prompt):
                raise RuntimeError("LLM 불가")

        gate = PMJudgmentGate()
        long_result = "충분한 내용이 있는 결과입니다. " * 4
        result = await gate.evaluate(
            "태스크", long_result, decision_client=FailingClient()
        )
        # LLM 실패 시 휴리스틱 폴백 → APPROVE
        assert result.verdict == JudgmentVerdict.APPROVE

    @pytest.mark.asyncio
    async def test_decision_client_approve(self):
        class MockClient:
            async def ask(self, prompt):
                return '{"verdict":"approve","reasoning":"충분함","suggested_dept":"","rework_prompt":""}'

        gate = PMJudgmentGate()
        long_result = "충분한 내용이 있는 결과입니다. " * 4
        result = await gate.evaluate("태스크", long_result, decision_client=MockClient())
        assert result.verdict == JudgmentVerdict.APPROVE

    @pytest.mark.asyncio
    async def test_decision_client_reroute(self):
        class MockClient:
            async def ask(self, prompt):
                return '{"verdict":"reroute","reasoning":"개발팀 필요","suggested_dept":"aiorg_engineering_bot","rework_prompt":""}'

        gate = PMJudgmentGate()
        long_result = "충분한 내용이 있는 결과입니다. " * 4
        result = await gate.evaluate("태스크", long_result, decision_client=MockClient())
        assert result.verdict == JudgmentVerdict.REROUTE
        assert result.suggested_dept == "aiorg_engineering_bot"

    @pytest.mark.asyncio
    async def test_decision_client_invalid_json_fallback(self):
        class MockClient:
            async def ask(self, prompt):
                return "invalid json response"

        gate = PMJudgmentGate()
        long_result = "충분한 내용이 있는 결과입니다. " * 4
        result = await gate.evaluate("태스크", long_result, decision_client=MockClient())
        # JSON 파싱 실패 → 휴리스틱 폴백
        assert result.verdict == JudgmentVerdict.APPROVE
