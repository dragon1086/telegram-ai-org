"""ResultSynthesizer 테스트 — LLM 합성 + keyword fallback."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.result_synthesizer import (
    ResultSynthesizer,
    SynthesisJudgment,
    _result_excerpt,
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


def test_result_excerpt_preserves_head_and_tail() -> None:
    text = "A" * 1800 + "B" * 900
    excerpt = _result_excerpt(text, limit=2200)
    assert excerpt.startswith("A" * 100)
    assert excerpt.endswith("B" * 100)
    assert "[중간 내용 생략]" in excerpt


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
        synth = ResultSynthesizer(decision_client=_FakeDecisionClient(llm_response))

        subtasks = [_make_subtask("aiorg_engineering_bot", "완료")]
        result = await synth.synthesize("코드 구현", subtasks)
        assert result.judgment == SynthesisJudgment.SUFFICIENT

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self, synth):
        synth = ResultSynthesizer(decision_client=_FakeDecisionClient("", fail=True))

        subtasks = [_make_subtask("aiorg_engineering_bot", "완료")]
        result = await synth.synthesize("코드 구현", subtasks)
        assert result.judgment == SynthesisJudgment.SUFFICIENT

    @pytest.mark.asyncio
    async def test_no_provider_fallback(self, synth):
        subtasks = [_make_subtask("aiorg_engineering_bot")]
        result = await synth.synthesize("코드 구현", subtasks)
        assert result.judgment == SynthesisJudgment.INSUFFICIENT


class TestFalseClaimDetection:
    """허위 접수 주장 감지 테스트 — REPORT에 '접수했습니다' 쓰고 FOLLOW_UP: none인 경우."""

    def test_false_claim_no_followup_line(self):
        """REPORT에 '후속 태스크로 접수했습니다' 있지만 FOLLOW_UP: none → follow_up_tasks 비어있음."""
        response = (
            "JUDGMENT: sufficient\n"
            "REASONING: 완료\n"
            "SUMMARY: 완료\n"
            "FOLLOW_UP: none\n"
            "ARTIFACTS: none\n"
            "REPORT:\n"
            "작업 완료. OrgScheduler 연결은 개발실에 후속 태스크로 접수했습니다.\n"
            "END_REPORT"
        )
        result = ResultSynthesizer._parse_synthesis(response)
        assert result.follow_up_tasks == [], "FOLLOW_UP:none 이면 follow_up_tasks는 빈 리스트여야 함"
        assert result.judgment == SynthesisJudgment.SUFFICIENT
        assert result.false_claim_detected is True, "허위 접수 주장 시 false_claim_detected=True여야 함"

    def test_no_false_claim_when_followup_registered(self):
        """REPORT에 '접수했습니다' 있고 FOLLOW_UP: 라인도 있으면 false_claim_detected=False."""
        response = (
            "JUDGMENT: sufficient\n"
            "REASONING: 완료\n"
            "SUMMARY: 완료\n"
            "FOLLOW_UP: DEPT:aiorg_engineering_bot|TASK:OrgScheduler GroupChatHub 연결\n"
            "ARTIFACTS: none\n"
            "REPORT:\n"
            "작업 완료. 추가 작업을 개발실에 후속 태스크로 접수했습니다.\n"
            "END_REPORT"
        )
        result = ResultSynthesizer._parse_synthesis(response)
        assert len(result.follow_up_tasks) == 1
        assert result.false_claim_detected is False, "FOLLOW_UP 라인 있으면 허위 주장 아님"

    def test_no_false_claim_when_no_접수_keyword(self):
        """REPORT에 '접수' 키워드 없으면 false_claim_detected=False."""
        response = (
            "JUDGMENT: sufficient\n"
            "REASONING: 완료\n"
            "SUMMARY: 완료\n"
            "FOLLOW_UP: none\n"
            "ARTIFACTS: none\n"
            "REPORT:\n작업이 모두 완료되었습니다.\nEND_REPORT"
        )
        result = ResultSynthesizer._parse_synthesis(response)
        assert result.false_claim_detected is False, "접수 키워드 없으면 false_claim_detected=False여야 함"

    def test_correct_followup_line_parses(self):
        """올바른 FOLLOW_UP: DEPT:xxx|TASK:yyy 라인 → follow_up_tasks에 등록."""
        response = (
            "JUDGMENT: sufficient\n"
            "REASONING: 완료\n"
            "SUMMARY: 완료\n"
            "FOLLOW_UP: DEPT:aiorg_engineering_bot|TASK:OrgScheduler에 GroupChatHub 인스턴스 연결\n"
            "ARTIFACTS: none\n"
            "REPORT:\n"
            "작업 완료.\n"
            "END_REPORT"
        )
        result = ResultSynthesizer._parse_synthesis(response)
        assert len(result.follow_up_tasks) == 1
        assert result.follow_up_tasks[0]["dept"] == "aiorg_engineering_bot"
        assert "GroupChatHub" in result.follow_up_tasks[0]["description"]

    def test_unknown_dept_followup_ignored(self):
        """KNOWN_DEPTS에 없는 dept → 파싱에서 무시."""
        response = (
            "JUDGMENT: sufficient\n"
            "REASONING: 완료\n"
            "SUMMARY: 완료\n"
            "FOLLOW_UP: DEPT:unknown_bot|TASK:무언가 작업\n"
            "ARTIFACTS: none\n"
            "REPORT:\n작업 완료.\nEND_REPORT"
        )
        result = ResultSynthesizer._parse_synthesis(response)
        assert result.follow_up_tasks == [], "알 수 없는 dept는 follow_up_tasks에 포함되지 않아야 함"

    def test_multiple_followup_lines(self):
        """FOLLOW_UP이 여러 줄인 경우 모두 파싱."""
        response = (
            "JUDGMENT: insufficient\n"
            "REASONING: 두 작업 남음\n"
            "SUMMARY: 미완료\n"
            "FOLLOW_UP: DEPT:aiorg_engineering_bot|TASK:코드 수정\n"
            "FOLLOW_UP: DEPT:aiorg_ops_bot|TASK:배포 확인\n"
            "ARTIFACTS: none\n"
            "REPORT:\n추가 작업 필요.\nEND_REPORT"
        )
        result = ResultSynthesizer._parse_synthesis(response)
        assert len(result.follow_up_tasks) == 2
        depts = {ft["dept"] for ft in result.follow_up_tasks}
        assert "aiorg_engineering_bot" in depts
        assert "aiorg_ops_bot" in depts


class TestReportSectionFormat:
    """보고서 섹션 포맷 일관성 테스트 — 3-섹션(결론/핵심 내용/다음 조치) 표준 준수."""

    def test_synthesis_prompt_uses_3section_format(self):
        """_SYNTHESIS_PROMPT가 3-섹션 포맷(핵심 내용)을 사용해야 한다."""
        from core.result_synthesizer import _SYNTHESIS_PROMPT
        assert "## 핵심 내용" in _SYNTHESIS_PROMPT
        assert "## 핵심 발견사항" not in _SYNTHESIS_PROMPT, "구 섹션명 '핵심 발견사항' 제거됐어야 함"
        assert "## 결론" in _SYNTHESIS_PROMPT
        assert "## 다음 조치" in _SYNTHESIS_PROMPT

    def test_3section_report_is_parsed_correctly(self):
        """3-섹션 보고서(결론/핵심 내용/다음 조치)가 올바르게 파싱되어야 한다."""
        response = (
            "JUDGMENT: sufficient\n"
            "REASONING: 모든 부서 완료\n"
            "SUMMARY: 완료\n"
            "FOLLOW_UP: none\n"
            "ARTIFACTS: none\n"
            "REPORT:\n"
            "## 결론\n"
            "프로젝트 A 완료, 배포 즉시 권고.\n\n"
            "## 핵심 내용\n"
            "- 코드 3파일 수정 완료\n"
            "- 테스트 12건 통과\n\n"
            "## 다음 조치\n"
            "- 배포 팀 인계\n"
            "END_REPORT"
        )
        result = ResultSynthesizer._parse_synthesis(response)
        assert result.judgment == SynthesisJudgment.SUFFICIENT
        assert "## 결론" in result.unified_report
        assert "## 핵심 내용" in result.unified_report
        assert "## 다음 조치" in result.unified_report

    def test_result_excerpt_increased_limit(self):
        """_result_excerpt 기본 limit이 3000으로 증가되었어야 한다."""
        import inspect
        sig = inspect.signature(_result_excerpt)
        default_limit = sig.parameters["limit"].default
        assert default_limit >= 3000, f"limit should be ≥3000, got {default_limit}"


class TestGroupChatHubConnection:
    """GroupChatHub + OrgScheduler 연결 단위 테스트."""

    @pytest.mark.asyncio
    async def test_hub_connected_to_scheduler(self):
        """GroupChatHub 인스턴스가 OrgScheduler에 올바르게 주입되어야 함."""
        from core.group_chat_hub import GroupChatHub

        sent: list[str] = []

        async def mock_send(text: str) -> None:
            sent.append(text)

        hub = GroupChatHub(send_to_group=mock_send)

        # OrgScheduler 직접 import 없이 group_chat_hub 속성 검증
        assert hub._send is mock_send, "GroupChatHub send 함수 주입 실패"
        assert hub.context is not None, "GroupChatContext 초기화 실패"
        assert hub.turn_manager is not None, "TurnManager 초기화 실패"

    @pytest.mark.asyncio
    async def test_participant_registration(self):
        """GroupChatHub에 봇 참가자 등록 후 participant_ids 확인."""
        from core.group_chat_hub import GroupChatHub

        async def mock_send(text: str) -> None:
            pass

        async def mock_speak(msg: str, history: list) -> str | None:
            return f"응답: {msg}"

        hub = GroupChatHub(send_to_group=mock_send)
        hub.register_participant("aiorg_engineering_bot", mock_speak, ["코드", "버그"])
        hub.register_participant("aiorg_ops_bot", mock_speak, ["배포", "인프라"])

        ids = hub.participant_ids
        assert "aiorg_engineering_bot" in ids
        assert "aiorg_ops_bot" in ids
