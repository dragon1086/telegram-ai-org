"""ResultSynthesizer 테스트 — LLM 합성 + keyword fallback."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.result_synthesizer import (
    ResultSynthesizer,
    SynthesisJudgment,
    SynthesisResult,
)


@pytest.fixture
def synth():
    return ResultSynthesizer()


def _make_subtask(dept: str, result: str | None = None) -> dict:
    return {
        "assigned_dept": dept,
        "result": result if result is not None else "(결과 없음)",
    }


class TestParseSynthesis:
    """_parse_synthesis 정적 메서드 테스트."""

    def test_sufficient_judgment(self, synth):
        response = (
            "JUDGMENT: sufficient\n"
            "REASONING: 모든 부서가 결과를 제출함\n"
            "SUMMARY: 개발실과 기획실이 작업을 완료함\n"
            "FOLLOW_UP: none\n"
            "REPORT:\n"
            "통합 보고서 내용입니다.\n"
            "END_REPORT"
        )
        result = synth._parse_synthesis(response)
        assert result.judgment == SynthesisJudgment.SUFFICIENT
        assert "모든 부서" in result.reasoning
        assert "통합 보고서" in result.unified_report

    def test_insufficient_with_follow_up(self, synth):
        response = (
            "JUDGMENT: insufficient\n"
            "REASONING: 개발실 결과 부족\n"
            "SUMMARY: 기획은 완료, 개발은 미완성\n"
            "FOLLOW_UP: DEPT:aiorg_engineering_bot|TASK:API 구현 완료 필요\n"
            "REPORT:\n"
            "부분 보고서\n"
            "END_REPORT"
        )
        result = synth._parse_synthesis(response)
        assert result.judgment == SynthesisJudgment.INSUFFICIENT
        assert len(result.follow_up_tasks) == 1
        assert result.follow_up_tasks[0]["dept"] == "aiorg_engineering_bot"
        assert "API 구현" in result.follow_up_tasks[0]["description"]

    def test_conflicting_judgment(self, synth):
        response = (
            "JUDGMENT: conflicting\n"
            "REASONING: 기획실과 개발실의 아키텍처 방향 불일치\n"
            "SUMMARY: 충돌 발견\n"
            "FOLLOW_UP: none\n"
            "REPORT:\n"
            "충돌 보고서\n"
            "END_REPORT"
        )
        result = synth._parse_synthesis(response)
        assert result.judgment == SynthesisJudgment.CONFLICTING

    def test_needs_integration(self, synth):
        response = (
            "JUDGMENT: needs_integration\n"
            "REASONING: 결과 통합 필요\n"
            "SUMMARY: 각 부서 결과를 하나로 합쳐야 함\n"
            "FOLLOW_UP: none\n"
            "REPORT:\n"
            "통합 보고서\n"
            "END_REPORT"
        )
        result = synth._parse_synthesis(response)
        assert result.judgment == SynthesisJudgment.NEEDS_INTEGRATION

    def test_multiple_follow_ups(self, synth):
        response = (
            "JUDGMENT: insufficient\n"
            "REASONING: 여러 부서 작업 부족\n"
            "SUMMARY: 요약\n"
            "FOLLOW_UP: DEPT:aiorg_engineering_bot|TASK:코드 보완\n"
            "DEPT:aiorg_design_bot|TASK:디자인 수정\n"
            "REPORT:\n"
            "보고서\n"
            "END_REPORT"
        )
        result = synth._parse_synthesis(response)
        assert len(result.follow_up_tasks) == 2

    def test_ignores_unknown_dept_in_follow_up(self, synth):
        response = (
            "JUDGMENT: insufficient\n"
            "REASONING: 이유\n"
            "SUMMARY: 요약\n"
            "FOLLOW_UP: DEPT:aiorg_unknown_bot|TASK:알 수 없는 부서\n"
            "REPORT:\n"
            "보고서\n"
            "END_REPORT"
        )
        result = synth._parse_synthesis(response)
        assert len(result.follow_up_tasks) == 0


class TestKeywordSynthesize:
    """keyword fallback 합성 테스트."""

    def test_all_results_present(self, synth):
        subtasks = [
            _make_subtask("aiorg_engineering_bot", "구현 완료"),
            _make_subtask("aiorg_product_bot", "기획 완료"),
        ]
        result = synth._keyword_synthesize(subtasks)
        assert result.judgment == SynthesisJudgment.SUFFICIENT
        assert "구현 완료" in result.unified_report
        assert "기획 완료" in result.unified_report

    def test_missing_result(self, synth):
        subtasks = [
            _make_subtask("aiorg_engineering_bot", "구현 완료"),
            _make_subtask("aiorg_product_bot"),  # 결과 없음
        ]
        result = synth._keyword_synthesize(subtasks)
        assert result.judgment == SynthesisJudgment.INSUFFICIENT
        assert "기획실" in result.reasoning

    def test_empty_string_result(self, synth):
        subtasks = [
            _make_subtask("aiorg_engineering_bot", ""),
        ]
        result = synth._keyword_synthesize(subtasks)
        assert result.judgment == SynthesisJudgment.INSUFFICIENT


class TestSynthesizeIntegration:
    """synthesize() LLM + fallback 통합 테스트."""

    @pytest.mark.asyncio
    async def test_llm_success(self, synth):
        llm_response = (
            "JUDGMENT: sufficient\n"
            "REASONING: 모든 결과 양호\n"
            "SUMMARY: 완료\n"
            "FOLLOW_UP: none\n"
            "REPORT:\n최종 보고서\nEND_REPORT"
        )
        with patch("core.result_synthesizer.get_provider") as mock_gp:
            mock_provider = AsyncMock()
            mock_provider.complete.return_value = llm_response
            mock_gp.return_value = mock_provider

            subtasks = [_make_subtask("aiorg_engineering_bot", "완료")]
            result = await synth.synthesize("코드 구현", subtasks)
            assert result.judgment == SynthesisJudgment.SUFFICIENT

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self, synth):
        with patch("core.result_synthesizer.get_provider") as mock_gp:
            mock_provider = AsyncMock()
            mock_provider.complete.side_effect = RuntimeError("API error")
            mock_gp.return_value = mock_provider

            subtasks = [_make_subtask("aiorg_engineering_bot", "완료")]
            result = await synth.synthesize("코드 구현", subtasks)
            assert result.judgment == SynthesisJudgment.SUFFICIENT

    @pytest.mark.asyncio
    async def test_no_provider_fallback(self, synth):
        with patch("core.result_synthesizer.get_provider", return_value=None):
            subtasks = [_make_subtask("aiorg_engineering_bot")]
            result = await synth.synthesize("코드 구현", subtasks)
            assert result.judgment == SynthesisJudgment.INSUFFICIENT
