"""태스크 유형 자율 분류 및 dispatch 메시지 단위 테스트.

Step 0 판단 체인 기반 8종 유형(조사/분석/기획/설계/검토/수정/구현/운영) 및
파일 변경 허용 필드가 올바르게 파싱·전파되는지 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pm_orchestrator import PMOrchestrator, SubTask
from core.structured_prompt import StructuredPrompt, StructuredPromptGenerator, TaskComplexity

# ─── _parse_decompose 유형 파싱 테스트 ──────────────────────────────────────

class TestParseDecompose:
    """_parse_decompose 가 TASK_TYPE / FILE_CHANGE 를 올바르게 파싱하는지 검증."""

    def _parse(self, response: str) -> list[SubTask]:
        return PMOrchestrator._parse_decompose(response)

    def test_parse_구현_file_change_yes(self):
        line = "DEPT:aiorg_engineering_bot|TASK:API 엔드포인트 구현|DEPENDS:none|TASK_TYPE:구현|FILE_CHANGE:yes"
        result = self._parse(line)
        assert len(result) == 1
        st = result[0]
        assert st.task_type == "구현"
        assert st.allow_file_change is True

    def test_parse_분석_file_change_no(self):
        line = "DEPT:aiorg_research_bot|TASK:경쟁사 분석 보고서 작성|DEPENDS:none|TASK_TYPE:분석|FILE_CHANGE:no"
        result = self._parse(line)
        assert len(result) == 1
        st = result[0]
        assert st.task_type == "분석"
        assert st.allow_file_change is False

    def test_parse_all_8_types(self):
        """8종 유형 모두 유효하게 파싱되는지."""
        types = ["조사", "분석", "기획", "설계", "검토", "수정", "구현", "운영"]
        for t in types:
            line = f"DEPT:aiorg_engineering_bot|TASK:태스크|DEPENDS:none|TASK_TYPE:{t}|FILE_CHANGE:no"
            result = self._parse(line)
            assert result[0].task_type == t, f"유형 {t} 파싱 실패"

    def test_invalid_task_type_becomes_none(self):
        """알 수 없는 유형은 None으로 처리 (무시)."""
        line = "DEPT:aiorg_engineering_bot|TASK:태스크|DEPENDS:none|TASK_TYPE:무효값|FILE_CHANGE:no"
        result = self._parse(line)
        assert result[0].task_type is None

    def test_file_change_inferred_from_task_type(self):
        """FILE_CHANGE 없을 때 task_type에서 자동 결정."""
        # 실행형: 구현 → True
        line = "DEPT:aiorg_engineering_bot|TASK:기능 구현|DEPENDS:none|TASK_TYPE:구현"
        result = self._parse(line)
        assert result[0].allow_file_change is True

        # 사고형: 분석 → False
        line = "DEPT:aiorg_research_bot|TASK:분석|DEPENDS:none|TASK_TYPE:분석"
        result = self._parse(line)
        assert result[0].allow_file_change is False

    def test_execution_types_allow_file_change(self):
        """실행형 3종(구현/수정/운영)은 file_change=yes."""
        for t in ["구현", "수정", "운영"]:
            line = f"DEPT:aiorg_engineering_bot|TASK:태스크|DEPENDS:none|TASK_TYPE:{t}|FILE_CHANGE:yes"
            result = self._parse(line)
            assert result[0].allow_file_change is True, f"{t} should allow file change"

    def test_thinking_types_deny_file_change(self):
        """사고형 5종(조사/분석/기획/설계/검토)은 file_change=no."""
        for t in ["조사", "분석", "기획", "설계", "검토"]:
            line = f"DEPT:aiorg_engineering_bot|TASK:태스크|DEPENDS:none|TASK_TYPE:{t}|FILE_CHANGE:no"
            result = self._parse(line)
            assert result[0].allow_file_change is False, f"{t} should not allow file change"

    def test_no_task_type_field_is_none(self):
        """TASK_TYPE 필드 없으면 None."""
        line = "DEPT:aiorg_engineering_bot|TASK:태스크|DEPENDS:none"
        result = self._parse(line)
        assert result[0].task_type is None
        assert result[0].allow_file_change is None

    def test_depends_on_parsed_correctly(self):
        """DEPENDS 파싱이 기존대로 동작하는지 (회귀 방지)."""
        line = "DEPT:aiorg_engineering_bot|TASK:구현|DEPENDS:0,1|TASK_TYPE:구현|FILE_CHANGE:yes"
        result = self._parse(line)
        assert result[0].depends_on == ["0", "1"]

    def test_multi_line_response(self):
        """멀티라인 LLM 응답 파싱."""
        response = (
            "DEPT:aiorg_research_bot|TASK:시장 조사|DEPENDS:none|TASK_TYPE:조사|FILE_CHANGE:no\n"
            "DEPT:aiorg_product_bot|TASK:PRD 작성|DEPENDS:0|TASK_TYPE:기획|FILE_CHANGE:no\n"
            "DEPT:aiorg_engineering_bot|TASK:API 구현|DEPENDS:1|TASK_TYPE:구현|FILE_CHANGE:yes"
        )
        result = self._parse(response)
        assert len(result) == 3
        assert result[0].task_type == "조사"
        assert result[1].task_type == "기획"
        assert result[2].task_type == "구현"
        assert result[2].allow_file_change is True
        assert result[0].allow_file_change is False

    def test_legacy_format_still_works(self):
        """이전 포맷(TASK_TYPE 없음)도 정상 파싱 — 하위 호환."""
        line = "DEPT:aiorg_engineering_bot|TASK:레거시 태스크|DEPENDS:none"
        result = self._parse(line)
        assert len(result) == 1
        assert result[0].description == "레거시 태스크"
        assert result[0].task_type is None


# ─── StructuredPrompt.render() 태스크 유형 경계 표시 테스트 ──────────────────

class TestStructuredPromptRender:
    """render()가 task_type 경계를 올바르게 포함하는지 검증."""

    def _make_prompt(
        self,
        task_type: str | None = None,
        allow_file_change: bool | None = None,
    ) -> StructuredPrompt:
        from core.structured_prompt import Phase
        return StructuredPrompt(
            complexity=TaskComplexity.SIMPLE,
            phases=[Phase(name="실행", instructions="수행하세요", order=1)],
            context="테스트 컨텍스트",
            task_type=task_type,
            allow_file_change=allow_file_change,
        )

    def test_render_includes_task_type_section(self):
        sp = self._make_prompt(task_type="분석", allow_file_change=False)
        rendered = sp.render()
        assert "[태스크 유형]" in rendered
        assert "유형: 분석" in rendered
        assert "파일·코드 변경 허용: 아니오" in rendered

    def test_render_구현_shows_file_change_yes(self):
        sp = self._make_prompt(task_type="구현", allow_file_change=True)
        rendered = sp.render()
        assert "파일·코드 변경 허용: 예" in rendered

    def test_render_without_task_type_no_type_section(self):
        """task_type 없으면 [태스크 유형] 섹션 미출력."""
        sp = self._make_prompt(task_type=None)
        rendered = sp.render()
        assert "[태스크 유형]" not in rendered

    def test_render_scope_warning_present(self):
        """범위 초과 경고 문구 존재."""
        sp = self._make_prompt(task_type="검토", allow_file_change=False)
        rendered = sp.render()
        assert "범위를 초과하는 작업" in rendered

    def test_render_context_still_present(self):
        """기존 컨텍스트/Phase 섹션이 그대로 유지되는지 (회귀 방지)."""
        sp = self._make_prompt(task_type="구현", allow_file_change=True)
        rendered = sp.render()
        assert "[배경]" in rendered
        assert "=== Phase 1: 실행 ===" in rendered


# ─── SubTask 기본 동작 테스트 ─────────────────────────────────────────────────

class TestSubTask:
    def test_default_task_type_is_none(self):
        st = SubTask(description="test", assigned_dept="aiorg_engineering_bot")
        assert st.task_type is None
        assert st.allow_file_change is None

    def test_task_type_set(self):
        st = SubTask(
            description="API 구현",
            assigned_dept="aiorg_engineering_bot",
            task_type="구현",
            allow_file_change=True,
        )
        assert st.task_type == "구현"
        assert st.allow_file_change is True


# ─── StructuredPromptGenerator.generate() 파라미터 전파 테스트 ───────────────

class TestStructuredPromptGeneratorTaskType:
    """generate()가 task_type/allow_file_change를 StructuredPrompt에 올바르게 전달하는지."""

    @pytest.mark.asyncio
    async def test_generate_propagates_task_type(self):
        gen = StructuredPromptGenerator(decision_client=None)  # LLM 없음 → template fallback
        sp = await gen.generate(
            description="경쟁사 시장 조사 및 분석",
            dept="aiorg_research_bot",
            task_type="분석",
            allow_file_change=False,
        )
        assert sp.task_type == "분석"
        assert sp.allow_file_change is False

    @pytest.mark.asyncio
    async def test_generate_without_task_type(self):
        gen = StructuredPromptGenerator(decision_client=None)
        sp = await gen.generate(
            description="코드 구현",
            dept="aiorg_engineering_bot",
        )
        assert sp.task_type is None
        assert sp.allow_file_change is None

    @pytest.mark.asyncio
    async def test_render_output_contains_type_when_set(self):
        gen = StructuredPromptGenerator(decision_client=None)
        sp = await gen.generate(
            description="설계 문서 작성",
            dept="aiorg_product_bot",
            task_type="설계",
            allow_file_change=False,
        )
        rendered = sp.render()
        assert "유형: 설계" in rendered
        assert "아니오" in rendered
