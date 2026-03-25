"""StructuredPromptGenerator 테스트 — 복잡도 감지 + Phase별 프롬프트 생성."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.structured_prompt import (
    Phase,
    StructuredPrompt,
    StructuredPromptGenerator,
    TaskComplexity,
)


class _FakeDecisionClient:
    def __init__(self, response: str, fail: bool = False) -> None:
        self.response = response
        self.fail = fail

    async def complete(self, prompt: str, *, system_prompt: str = "", workdir: str | None = None) -> str:
        if self.fail:
            raise RuntimeError("API error")
        return self.response


@pytest.fixture
def gen():
    return StructuredPromptGenerator()


class TestComplexityDetection:
    """detect_complexity 테스트."""

    def test_simple_task(self, gen):
        assert gen.detect_complexity("버그 수정") == TaskComplexity.SIMPLE

    def test_moderate_task(self, gen):
        assert gen.detect_complexity("API 엔드포인트 구현하고 테스트 작성") == TaskComplexity.MODERATE

    def test_complex_task(self, gen):
        assert gen.detect_complexity("시스템 아키텍처 설계 및 마이그레이션 계획") == TaskComplexity.COMPLEX

    def test_long_description_is_complex(self, gen):
        long_desc = " ".join(["작업"] * 60)  # 60 words
        assert gen.detect_complexity(long_desc) == TaskComplexity.COMPLEX

    def test_medium_description_is_moderate(self, gen):
        med_desc = " ".join(["작업"] * 25)  # 25 words
        assert gen.detect_complexity(med_desc) == TaskComplexity.MODERATE


class TestTemplateGeneration:
    """_template_generate fallback 테스트."""

    def test_simple_has_one_phase(self, gen):
        result = gen._template_generate(
            "버그 수정", "aiorg_engineering_bot", TaskComplexity.SIMPLE, "",
        )
        assert len(result.phases) == 1
        assert result.complexity == TaskComplexity.SIMPLE

    def test_moderate_has_multiple_phases(self, gen):
        result = gen._template_generate(
            "API 구현", "aiorg_engineering_bot", TaskComplexity.MODERATE, "",
        )
        assert len(result.phases) >= 2

    def test_complex_has_four_plus_phases(self, gen):
        result = gen._template_generate(
            "아키텍처 설계", "aiorg_engineering_bot", TaskComplexity.COMPLEX, "",
        )
        assert len(result.phases) >= 4

    def test_all_depts_have_templates(self, gen):
        depts = [
            "aiorg_product_bot", "aiorg_engineering_bot",
            "aiorg_design_bot", "aiorg_growth_bot", "aiorg_ops_bot",
        ]
        for dept in depts:
            result = gen._template_generate(
                "작업", dept, TaskComplexity.MODERATE, "",
            )
            assert len(result.phases) >= 2, f"{dept} should have phases"

    def test_unknown_dept_uses_default(self, gen):
        result = gen._template_generate(
            "작업", "unknown_bot", TaskComplexity.SIMPLE, "",
        )
        assert len(result.phases) == 1

    def test_phases_contain_description(self, gen):
        result = gen._template_generate(
            "로그인 페이지 디자인", "aiorg_design_bot", TaskComplexity.MODERATE, "",
        )
        for phase in result.phases:
            assert "로그인 페이지 디자인" in phase.instructions


class TestRender:
    """StructuredPrompt.render() 테스트."""

    def test_basic_render(self):
        prompt = StructuredPrompt(
            complexity=TaskComplexity.SIMPLE,
            phases=[Phase("실행", "코드를 작성하세요", ["코드"], order=1)],
            context="API 개발 프로젝트",
            constraints=["엔진 특화 명령어 사용 금지"],
        )
        rendered = prompt.render()
        assert "[배경]" in rendered
        assert "API 개발 프로젝트" in rendered
        assert "[제약]" in rendered
        assert "Phase 1: 실행" in rendered
        assert "코드를 작성하세요" in rendered
        assert "산출물: 코드" in rendered

    def test_multi_phase_ordering(self):
        prompt = StructuredPrompt(
            complexity=TaskComplexity.MODERATE,
            phases=[
                Phase("검증", "검증하세요", ["결과"], order=2),
                Phase("분석", "분석하세요", ["보고서"], order=1),
            ],
        )
        rendered = prompt.render()
        # Phase 1이 Phase 2보다 먼저
        pos1 = rendered.index("Phase 1")
        pos2 = rendered.index("Phase 2")
        assert pos1 < pos2

    def test_engine_agnostic(self):
        """렌더링된 프롬프트에 엔진 특화 명령어가 없어야 함."""
        gen = StructuredPromptGenerator()
        result = gen._template_generate(
            "대규모 시스템 아키텍처 설계", "aiorg_engineering_bot",
            TaskComplexity.COMPLEX, "",
        )
        rendered = result.render()
        engine_commands = ["/team", "/ralph", "/ultrawork", "codex ", "claude code"]
        for cmd in engine_commands:
            assert cmd not in rendered.lower(), f"Engine command '{cmd}' found in prompt"


class TestLLMGeneration:
    """LLM 기반 프롬프트 생성 테스트."""

    @pytest.mark.asyncio
    async def test_llm_success(self, gen):
        llm_response = (
            "PHASE:분석|INSTRUCTIONS:현재 코드를 분석하세요|DELIVERABLES:분석 보고서\n"
            "PHASE:구현|INSTRUCTIONS:기능을 구현하세요|DELIVERABLES:구현 코드,테스트"
        )
        gen = StructuredPromptGenerator(decision_client=_FakeDecisionClient(llm_response))

        result = await gen.generate("API 구현", "aiorg_engineering_bot")
        assert len(result.phases) == 2
        assert result.phases[0].name == "분석"
        assert result.phases[1].name == "구현"
        assert "테스트" in result.phases[1].deliverables

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self, gen):
        gen = StructuredPromptGenerator(decision_client=_FakeDecisionClient("", fail=True))
        result = await gen.generate("API 구현", "aiorg_engineering_bot")
        assert len(result.phases) >= 1  # fallback template

    @pytest.mark.asyncio
    async def test_no_provider_falls_back(self, gen):
        result = await gen.generate("디자인 작업", "aiorg_design_bot")
        assert len(result.phases) >= 1

    @pytest.mark.asyncio
    async def test_llm_empty_response_falls_back(self, gen):
        gen = StructuredPromptGenerator(decision_client=_FakeDecisionClient("I don't understand"))
        result = await gen.generate("작업", "aiorg_product_bot")
        assert len(result.phases) >= 1  # fallback


class TestParsePhases:
    """_parse_phases 정적 메서드 테스트."""

    def test_single_phase(self, gen):
        response = "PHASE:분석|INSTRUCTIONS:코드 분석|DELIVERABLES:보고서"
        phases = gen._parse_phases(response)
        assert len(phases) == 1
        assert phases[0].order == 1

    def test_empty_response(self, gen):
        assert gen._parse_phases("random text") == []

    def test_missing_instructions(self, gen):
        response = "PHASE:분석|DELIVERABLES:보고서"
        assert gen._parse_phases(response) == []

    def test_no_deliverables(self, gen):
        response = "PHASE:분석|INSTRUCTIONS:분석하세요|DELIVERABLES:"
        phases = gen._parse_phases(response)
        assert len(phases) == 1
        assert phases[0].deliverables == []
