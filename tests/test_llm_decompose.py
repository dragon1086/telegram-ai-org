"""LLM 분해 + 키워드 fallback 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pm_orchestrator import KNOWN_DEPTS, PMOrchestrator


class _FakeDecisionClient:
    def __init__(self, response: str, fail: bool = False) -> None:
        self.response = response
        self.fail = fail

    async def complete(self, prompt: str, *, system_prompt: str = "", workdir: str | None = None) -> str:
        if self.fail:
            raise RuntimeError("API error")
        return self.response


class TestParseDecompose:
    """_parse_decompose 정적 메서드 테스트."""

    def test_single_dept(self):
        response = "DEPT:aiorg_engineering_bot|TASK:API 엔드포인트 구현|DEPENDS:none"
        result = PMOrchestrator._parse_decompose(response)
        assert len(result) == 1
        assert result[0].assigned_dept == "aiorg_engineering_bot"
        assert result[0].description == "API 엔드포인트 구현"
        assert result[0].depends_on == []

    def test_multiple_depts_with_deps(self):
        response = (
            "DEPT:aiorg_product_bot|TASK:요구사항 정리|DEPENDS:none\n"
            "DEPT:aiorg_design_bot|TASK:UI 와이어프레임 작성|DEPENDS:0\n"
            "DEPT:aiorg_engineering_bot|TASK:프론트엔드 구현|DEPENDS:0,1"
        )
        result = PMOrchestrator._parse_decompose(response)
        assert len(result) == 3
        assert result[0].depends_on == []
        assert result[1].depends_on == ["0"]
        assert result[2].depends_on == ["0", "1"]

    def test_ignores_unknown_dept(self):
        response = (
            "DEPT:aiorg_engineering_bot|TASK:유효한 태스크|DEPENDS:none\n"
            "DEPT:aiorg_unknown_bot|TASK:잘못된 부서|DEPENDS:none"
        )
        result = PMOrchestrator._parse_decompose(response)
        assert len(result) == 1
        assert result[0].assigned_dept == "aiorg_engineering_bot"

    def test_ignores_malformed_lines(self):
        response = (
            "Some preamble text\n"
            "DEPT:aiorg_engineering_bot|TASK:유효한 태스크|DEPENDS:none\n"
            "random garbage\n"
            "DEPT:|TASK:|DEPENDS:none\n"
        )
        result = PMOrchestrator._parse_decompose(response)
        assert len(result) == 1

    def test_empty_response(self):
        result = PMOrchestrator._parse_decompose("")
        assert result == []

    def test_no_depends_field(self):
        """DEPENDS 필드 없이도 파싱 가능."""
        response = "DEPT:aiorg_product_bot|TASK:기획서 작성"
        result = PMOrchestrator._parse_decompose(response)
        assert len(result) == 1
        assert result[0].depends_on == []

    def test_all_five_depts(self):
        lines = []
        for dept in KNOWN_DEPTS:
            lines.append(f"DEPT:{dept}|TASK:{dept} 작업|DEPENDS:none")
        response = "\n".join(lines)
        result = PMOrchestrator._parse_decompose(response)
        assert len(result) == len(KNOWN_DEPTS)


class TestKeywordDecompose:
    """_keyword_decompose fallback 테스트."""

    @pytest.fixture
    def orch(self):
        return PMOrchestrator(
            context_db=MagicMock(),
            task_graph=MagicMock(),
            claim_manager=MagicMock(),
            memory=MagicMock(),
            org_id="pm",
            telegram_send_func=AsyncMock(),
        )

    def test_engineering_keyword(self, orch):
        result = orch._keyword_decompose("코드 구현해줘")
        assert len(result) == 1
        assert result[0].assigned_dept == "aiorg_engineering_bot"

    def test_design_keyword(self, orch):
        result = orch._keyword_decompose("UI 디자인 만들어줘")
        assert len(result) == 1
        assert result[0].assigned_dept == "aiorg_design_bot"

    def test_multiple_keywords(self, orch):
        result = orch._keyword_decompose("기획하고 개발하고 배포까지")
        depts = {st.assigned_dept for st in result}
        assert "aiorg_product_bot" in depts
        assert "aiorg_engineering_bot" in depts
        assert "aiorg_ops_bot" in depts

    def test_no_keyword_defaults_to_product(self, orch):
        result = orch._keyword_decompose("뭔가 해줘")
        assert len(result) == 1
        assert result[0].assigned_dept == "aiorg_product_bot"

    def test_dependency_chain(self, orch):
        """기획 → 디자인 → 개발 의존성 체인."""
        result = orch._keyword_decompose("기획부터 디자인, 개발까지")
        # 기획이 먼저, 디자인은 기획에 의존, 개발은 기획+디자인에 의존
        assert result[0].assigned_dept == "aiorg_product_bot"
        assert result[0].depends_on == []
        assert result[1].assigned_dept == "aiorg_design_bot"
        assert "0" in result[1].depends_on


class TestDecomposeIntegration:
    """decompose() LLM + fallback 통합 테스트."""

    @pytest.fixture
    def orch(self):
        return PMOrchestrator(
            context_db=MagicMock(),
            task_graph=MagicMock(),
            claim_manager=MagicMock(),
            memory=MagicMock(),
            org_id="pm",
            telegram_send_func=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_llm_success(self, orch):
        """LLM이 성공하면 LLM 결과 사용."""
        orch = PMOrchestrator(
            context_db=MagicMock(),
            task_graph=MagicMock(),
            claim_manager=MagicMock(),
            memory=MagicMock(),
            org_id="pm",
            telegram_send_func=AsyncMock(),
            decision_client=_FakeDecisionClient(
                "DEPT:aiorg_engineering_bot|TASK:LLM이 생성한 구체적 지시|DEPENDS:none"
            ),
        )

        result = await orch.decompose("코드 짜줘")
        assert len(result) == 1
        assert "LLM이 생성한 구체적 지시" in result[0].description

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self, orch):
        """LLM 실패 시 키워드 fallback."""
        orch = PMOrchestrator(
            context_db=MagicMock(),
            task_graph=MagicMock(),
            claim_manager=MagicMock(),
            memory=MagicMock(),
            org_id="pm",
            telegram_send_func=AsyncMock(),
            decision_client=_FakeDecisionClient("", fail=True),
        )

        result = await orch.decompose("코드 개발해줘")
        assert len(result) >= 1
        assert result[0].assigned_dept == "aiorg_engineering_bot"

    @pytest.mark.asyncio
    async def test_no_provider_falls_back(self, orch):
        """LLM provider 없으면 키워드 fallback."""
        result = await orch.decompose("디자인 해줘")
        assert len(result) >= 1
        assert result[0].assigned_dept == "aiorg_design_bot"

    @pytest.mark.asyncio
    async def test_llm_empty_response_falls_back(self, orch):
        """LLM이 빈 응답 → fallback."""
        orch = PMOrchestrator(
            context_db=MagicMock(),
            task_graph=MagicMock(),
            claim_manager=MagicMock(),
            memory=MagicMock(),
            org_id="pm",
            telegram_send_func=AsyncMock(),
            decision_client=_FakeDecisionClient("I don't understand"),
        )

        result = await orch.decompose("기획서 써줘")
        assert len(result) >= 1
        assert result[0].assigned_dept == "aiorg_product_bot"
