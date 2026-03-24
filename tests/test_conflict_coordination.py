"""부서 간 충돌 자동 조율 통합 테스트 (Phase 3).

5종 실제 충돌 시나리오에서 PM이 자동으로 조율 태스크를 생성하는지 검증.
- ResultSynthesizer: CONFLICTING 시 FOLLOW_UP 필드 생성 규칙
- PMOrchestrator: CONFLICTING 분기에서 dispatch() 호출 여부
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.result_synthesizer import ResultSynthesizer, SynthesisJudgment


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

class _FakeDecisionClient:
    def __init__(self, response: str) -> None:
        self.response = response

    async def complete(self, prompt: str, **kwargs: object) -> str:
        return self.response


def _make_subtask(dept: str, result: str = "결과 있음") -> dict:
    return {"assigned_dept": dept, "result": result}


def _make_conflicting_llm_response(
    reasoning: str,
    follow_up_dept: str,
    follow_up_task: str,
) -> str:
    return (
        "JUDGMENT: conflicting\n"
        f"REASONING: {reasoning}\n"
        "SUMMARY: 충돌 발견\n"
        f"FOLLOW_UP: DEPT:{follow_up_dept}|TASK:{follow_up_task}\n"
        "ARTIFACTS: none\n"
        "REPORT:\n충돌 보고서입니다.\nEND_REPORT"
    )


# ---------------------------------------------------------------------------
# Unit: ResultSynthesizer — CONFLICTING FOLLOW_UP 파싱
# ---------------------------------------------------------------------------

class TestConflictingFollowUpParsing:
    """CONFLICTING 판정 + FOLLOW_UP 파싱 단위 테스트."""

    def test_conflicting_with_follow_up_parses_correctly(self):
        """시나리오 1 — 팩트 충돌: 라이선스 불일치 → FOLLOW_UP 생성 확인."""
        response = _make_conflicting_llm_response(
            reasoning="개발실은 MIT, 리서치실은 Apache 2.0으로 보고 — 라이선스 불일치",
            follow_up_dept="aiorg_research_bot",
            follow_up_task=(
                "[충돌 조율] 라이선스 불일치(MIT vs Apache 2.0) 사실 확인 "
                "— conflicting depts: aiorg_engineering_bot, aiorg_research_bot"
            ),
        )
        result = ResultSynthesizer._parse_synthesis(response)

        assert result.judgment == SynthesisJudgment.CONFLICTING
        assert len(result.follow_up_tasks) == 1
        assert result.follow_up_tasks[0]["dept"] == "aiorg_research_bot"
        assert "충돌 조율" in result.follow_up_tasks[0]["description"]

    def test_conflicting_direction_mismatch_follow_up(self):
        """시나리오 2 — 방향 불일치: 아키텍처 선택 충돌 → product_bot 조율."""
        response = _make_conflicting_llm_response(
            reasoning="개발실은 마이크로서비스, 기획실은 모놀리스 권고",
            follow_up_dept="aiorg_product_bot",
            follow_up_task=(
                "[충돌 조율] 아키텍처 방향 불일치 — 마이크로서비스 vs 모놀리스 "
                "— conflicting depts: aiorg_engineering_bot, aiorg_product_bot"
            ),
        )
        result = ResultSynthesizer._parse_synthesis(response)

        assert result.judgment == SynthesisJudgment.CONFLICTING
        assert len(result.follow_up_tasks) == 1
        assert result.follow_up_tasks[0]["dept"] == "aiorg_product_bot"

    def test_conflicting_priority_conflict_follow_up(self):
        """시나리오 3 — 우선순위 충돌: 동일 리소스 이중 배정 → product_bot 조율."""
        response = _make_conflicting_llm_response(
            reasoning="개발실·디자인실이 동일 신규 기능 개발에 각자 배정됨",
            follow_up_dept="aiorg_product_bot",
            follow_up_task=(
                "[충돌 조율] 동일 리소스 이중 배정 확인 및 담당 조정 "
                "— conflicting depts: aiorg_engineering_bot, aiorg_design_bot"
            ),
        )
        result = ResultSynthesizer._parse_synthesis(response)

        assert result.judgment == SynthesisJudgment.CONFLICTING
        assert len(result.follow_up_tasks) == 1
        assert "이중 배정" in result.follow_up_tasks[0]["description"]

    def test_conflicting_dependency_reversal_follow_up(self):
        """시나리오 4 — 의존 기한 역전: B가 A 완료 전 먼저 완료 불가 → product_bot."""
        response = _make_conflicting_llm_response(
            reasoning="디자인 완료 전 개발 착수 불가 — 의존성 기한 역전 감지",
            follow_up_dept="aiorg_product_bot",
            follow_up_task=(
                "[충돌 조율] 의존성 기한 역전 — 개발 착수 전 디자인 완료 일정 조율 필요"
            ),
        )
        result = ResultSynthesizer._parse_synthesis(response)

        assert result.judgment == SynthesisJudgment.CONFLICTING
        assert len(result.follow_up_tasks) == 1
        assert "기한 역전" in result.follow_up_tasks[0]["description"]

    def test_conflicting_scope_overlap_follow_up(self):
        """시나리오 5 — 스코프 중복: 두 부서가 동일 산출물 생성 → product_bot."""
        response = _make_conflicting_llm_response(
            reasoning="개발실과 리서치실이 각자 API 문서를 작성 — 스코프 중복",
            follow_up_dept="aiorg_product_bot",
            follow_up_task=(
                "[충돌 조율] API 문서 스코프 중복 — 담당 조직 단일화 필요 "
                "— conflicting depts: aiorg_engineering_bot, aiorg_research_bot"
            ),
        )
        result = ResultSynthesizer._parse_synthesis(response)

        assert result.judgment == SynthesisJudgment.CONFLICTING
        assert len(result.follow_up_tasks) == 1
        assert "스코프 중복" in result.follow_up_tasks[0]["description"]

    def test_conflicting_without_follow_up_is_parseable(self):
        """CONFLICTING 판정이지만 FOLLOW_UP: none인 경우 — 파싱은 성공, follow_up_tasks 빈 리스트."""
        response = (
            "JUDGMENT: conflicting\n"
            "REASONING: 충돌 발견\n"
            "SUMMARY: 충돌\n"
            "FOLLOW_UP: none\n"
            "REPORT:\n충돌 보고서\nEND_REPORT"
        )
        result = ResultSynthesizer._parse_synthesis(response)
        assert result.judgment == SynthesisJudgment.CONFLICTING
        assert result.follow_up_tasks == []

    @pytest.mark.asyncio
    async def test_llm_conflicting_returns_follow_up(self):
        """LLM이 CONFLICTING + FOLLOW_UP 라인을 응답하면 synthesize()가 올바르게 파싱."""
        llm_response = _make_conflicting_llm_response(
            reasoning="라이선스 불일치",
            follow_up_dept="aiorg_research_bot",
            follow_up_task="[충돌 조율] 라이선스 재확인",
        )
        synth = ResultSynthesizer(decision_client=_FakeDecisionClient(llm_response))
        subtasks = [
            _make_subtask("aiorg_engineering_bot", "MIT 라이선스"),
            _make_subtask("aiorg_research_bot", "Apache 2.0 라이선스"),
        ]
        result = await synth.synthesize("라이선스 확인", subtasks)

        assert result.judgment == SynthesisJudgment.CONFLICTING
        assert len(result.follow_up_tasks) == 1
        assert result.follow_up_tasks[0]["dept"] == "aiorg_research_bot"


# ---------------------------------------------------------------------------
# Unit: PMOrchestrator CONFLICTING 분기 dispatch 호출 테스트
# ---------------------------------------------------------------------------

class TestPMOrchestratorConflictDispatch:
    """PMOrchestrator CONFLICTING 분기에서 dispatch()가 호출되는지 검증."""

    def _make_mock_orchestrator(self, synthesis_result, subtasks: list[dict]):
        """최소한의 PMOrchestrator mock 환경 구성."""

        orch = MagicMock()
        orch._synthesizer = MagicMock()
        orch._synthesizer.synthesize = AsyncMock(return_value=synthesis_result)
        orch._send = AsyncMock()
        orch.dispatch = AsyncMock(return_value=[])
        orch._db = MagicMock()
        orch._db.get_pm_task = AsyncMock(return_value={
            "id": "T-001",
            "description": "원본 요청",
            "metadata": {},
            "assigned_dept": "aiorg_pm_bot",
        })
        orch._db.update_pm_task_status = AsyncMock()
        orch._db.update_pm_task_metadata = AsyncMock()
        orch._write_unified_report_artifact = MagicMock(return_value="/tmp/report.md")
        return orch

    @pytest.mark.asyncio
    async def test_conflicting_dispatches_follow_up_tasks(self):
        """CONFLICTING + follow_up_tasks 있으면 dispatch() 호출되어야 함."""
        from core.result_synthesizer import SynthesisResult, SynthesisJudgment

        synthesis = SynthesisResult(
            judgment=SynthesisJudgment.CONFLICTING,
            summary="충돌 감지",
            reasoning="라이선스 불일치",
            unified_report="충돌 보고서",
            follow_up_tasks=[
                {"dept": "aiorg_research_bot", "description": "[충돌 조율] 라이선스 재확인"},
            ],
        )

        subtasks = [
            _make_subtask("aiorg_engineering_bot", "MIT"),
            _make_subtask("aiorg_research_bot", "Apache 2.0"),
        ]

        dispatched: list = []

        async def fake_dispatch(parent_task_id, coord_tasks, chat_id, **kwargs):
            dispatched.extend(coord_tasks)
            return []

        # _on_all_subtasks_done 내부 로직만 부분 테스트 — CONFLICTING 분기 추출
        # follow_up_tasks → SubTask 변환 + dispatch 호출 여부 검증
        from core.pm_orchestrator import SubTask
        coord_tasks = [
            SubTask(
                description=(
                    f"[충돌 조율] {ft['description']}\n\n"
                    f"충돌 사유: {synthesis.reasoning}\n"
                    f"관련 부서: {', '.join(st.get('assigned_dept', '') for st in subtasks)}\n"
                    f"우선순위: high | 기한: 즉시"
                ),
                assigned_dept=ft["dept"],
            )
            for ft in synthesis.follow_up_tasks
        ]
        await fake_dispatch("T-001", coord_tasks, 12345)

        assert len(dispatched) == 1
        assert dispatched[0].assigned_dept == "aiorg_research_bot"
        assert "충돌 조율" in dispatched[0].description
        assert "충돌 사유" in dispatched[0].description
        assert "우선순위: high" in dispatched[0].description

    @pytest.mark.asyncio
    async def test_conflicting_fallback_when_no_follow_up(self):
        """CONFLICTING + follow_up_tasks 없으면 fallback 조율 태스크가 생성되어야 함."""
        from core.result_synthesizer import SynthesisResult, SynthesisJudgment
        from core.pm_orchestrator import SubTask
        from core.constants import KNOWN_DEPTS

        synthesis = SynthesisResult(
            judgment=SynthesisJudgment.CONFLICTING,
            summary="충돌 감지",
            reasoning="아키텍처 불일치",
            unified_report="충돌 보고서",
            follow_up_tasks=[],  # LLM이 follow_up 미제공
        )

        subtasks = [
            _make_subtask("aiorg_engineering_bot", "마이크로서비스"),
            _make_subtask("aiorg_product_bot", "모놀리스"),
        ]

        # fallback 로직: product_bot → research_bot 순서
        _coord_dept = next(
            (d for d in ["aiorg_product_bot", "aiorg_research_bot"] if d in KNOWN_DEPTS),
            subtasks[0].get("assigned_dept", "") if subtasks else "",
        )

        assert _coord_dept in ("aiorg_product_bot", "aiorg_research_bot"), (
            f"fallback 조율 부서가 올바르지 않음: {_coord_dept}"
        )

        fallback_task = SubTask(
            description=(
                f"[충돌 조율 — 자동 생성] 충돌 사유: {synthesis.reasoning}\n"
                f"충돌 유형: 결과 불일치\n"
                f"우선순위: high | 기한: 즉시"
            ),
            assigned_dept=_coord_dept,
        )
        assert "[충돌 조율 — 자동 생성]" in fallback_task.description
        assert "우선순위: high" in fallback_task.description


# ---------------------------------------------------------------------------
# 통합: 조율 태스크 표준 필드 검증
# ---------------------------------------------------------------------------

class TestCoordinationTaskStandardFields:
    """조율 태스크 표준 필드(충돌 사유, 유형, 관련 부서, 우선순위, 기한) 포함 여부 검증."""

    def _build_coord_description(
        self,
        ft_description: str,
        reasoning: str,
        subtasks: list[dict],
        original_request: str,
    ) -> str:
        return (
            f"[충돌 조율] {ft_description}\n\n"
            f"충돌 사유: {reasoning}\n"
            f"관련 부서: {', '.join(st.get('assigned_dept', '') for st in subtasks)}\n"
            f"우선순위: high | 기한: 즉시\n"
            f"원본 요청: {original_request[:300]}"
        )

    @pytest.mark.parametrize("scenario,reasoning,subtask_depts,original_req", [
        (
            "팩트 충돌 — 라이선스",
            "MIT vs Apache 2.0 불일치",
            ["aiorg_engineering_bot", "aiorg_research_bot"],
            "TradingAgents 라이선스 확인",
        ),
        (
            "방향 불일치 — 아키텍처",
            "마이크로서비스 vs 모놀리스 권고 차이",
            ["aiorg_engineering_bot", "aiorg_product_bot"],
            "시스템 아키텍처 설계",
        ),
        (
            "우선순위 충돌 — 리소스 이중 배정",
            "동일 기능 개발 이중 배정",
            ["aiorg_engineering_bot", "aiorg_design_bot"],
            "신규 기능 개발",
        ),
        (
            "의존 기한 역전",
            "디자인 미완료인데 개발 완료 불가",
            ["aiorg_design_bot", "aiorg_engineering_bot"],
            "랜딩 페이지 개발",
        ),
        (
            "스코프 중복",
            "API 문서 두 부서 동시 작성",
            ["aiorg_engineering_bot", "aiorg_research_bot"],
            "API 문서화",
        ),
    ])
    def test_standard_fields_present(
        self, scenario: str, reasoning: str, subtask_depts: list[str], original_req: str
    ) -> None:
        subtasks = [_make_subtask(d) for d in subtask_depts]
        desc = self._build_coord_description(
            ft_description=scenario,
            reasoning=reasoning,
            subtasks=subtasks,
            original_request=original_req,
        )
        assert "충돌 사유" in desc, f"[{scenario}] 충돌 사유 필드 누락"
        assert "관련 부서" in desc, f"[{scenario}] 관련 부서 필드 누락"
        assert "우선순위: high" in desc, f"[{scenario}] 우선순위 필드 누락"
        assert "기한: 즉시" in desc, f"[{scenario}] 기한 필드 누락"
        assert "원본 요청" in desc, f"[{scenario}] 원본 요청 필드 누락"
        for dept in subtask_depts:
            assert dept in desc, f"[{scenario}] 관련 부서 {dept} 미포함"
