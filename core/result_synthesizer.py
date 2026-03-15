"""PM 결과 합성기 — 부서 결과를 LLM으로 분석·판단·후속 조치.

consolidate_results()의 단순 연결을 대체하여:
1. LLM으로 부서 결과를 분석
2. 판단 (sufficient/insufficient/conflicting/needs_integration)
3. 판단에 따른 자동 후속 조치 (추가 태스크, 통합 보고서 등)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from core.llm_provider import get_provider
from core.constants import KNOWN_DEPTS
from core.pm_decision import DecisionClientProtocol


class SynthesisJudgment(str, Enum):
    """결과 합성 판단."""
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"
    NEEDS_INTEGRATION = "needs_integration"


@dataclass
class SynthesisResult:
    """합성 결과."""
    judgment: SynthesisJudgment
    summary: str
    follow_up_tasks: list[dict] = field(default_factory=list)  # [{dept, description}]
    unified_report: str = ""
    reasoning: str = ""


_SYNTHESIS_PROMPT = (
    "You are a PM synthesizing results from multiple departments.\n\n"
    "ORIGINAL REQUEST: {original_request}\n\n"
    "DEPARTMENT RESULTS:\n{dept_results}\n\n"
    "Analyze the results and respond in this EXACT format:\n"
    "JUDGMENT: sufficient | insufficient | conflicting | needs_integration\n"
    "REASONING: one-line explanation of your judgment\n"
    "SUMMARY: unified summary of all results (2-3 sentences)\n"
    "FOLLOW_UP: DEPT:aiorg_xxx_bot|TASK:description (one per line, or 'none')\n"
    "REPORT:\n"
    "final integrated report for the user\n"
    "END_REPORT\n\n"
    "Rules:\n"
    "- SUFFICIENT: all departments delivered what was needed\n"
    "- INSUFFICIENT: key deliverables missing or incomplete\n"
    "- CONFLICTING: departments contradict each other\n"
    "- NEEDS_INTEGRATION: results are good but need to be combined into one coherent output\n"
    "- Write in Korean\n"
  "- IMPORTANT: Even when SUFFICIENT, scan all reports for future plans\n"
  "  (향후 계획/다음 단계/추가 작업/진행 예정/예정 등) and add them as FOLLOW_UP tasks.\n"
  "  Assign each to the most relevant dept (aiorg_design_bot/aiorg_engineering_bot/\n"
  "  aiorg_growth_bot/aiorg_ops_bot/aiorg_product_bot). If truly none, write FOLLOW_UP: none\n"
)


class ResultSynthesizer:
    """부서 결과를 LLM으로 분석·판단하는 합성기."""

    def __init__(self, decision_client: DecisionClientProtocol | None = None) -> None:
        self._decision_client = decision_client

    async def synthesize(
        self, original_request: str, subtasks: list[dict],
    ) -> SynthesisResult:
        """부서 결과를 분석·판단. LLM 실패 시 keyword fallback."""
        result = await self._llm_synthesize(original_request, subtasks)
        if result is not None:
            return result
        return self._keyword_synthesize(subtasks)

    async def _llm_synthesize(
        self, original_request: str, subtasks: list[dict],
    ) -> SynthesisResult | None:
        """LLM 기반 합성. 실패 시 None."""
        provider = None if self._decision_client is not None else get_provider()
        if self._decision_client is None and provider is None:
            return None

        dept_results = "\n".join(
            f"- [{KNOWN_DEPTS.get(st.get('assigned_dept', ''), st.get('assigned_dept', '?'))}]: "
            f"{st.get('result', '(결과 없음)')[:300]}"
            for st in subtasks
        )

        prompt = _SYNTHESIS_PROMPT.format(
            original_request=original_request[:500],
            dept_results=dept_results,
        )

        try:
            if self._decision_client is not None:
                response = await asyncio.wait_for(
                    self._decision_client.complete(prompt),
                    timeout=45.0,
                )
            else:
                response = await asyncio.wait_for(
                    provider.complete(prompt, timeout=20.0),
                    timeout=25.0,
                )
            return self._parse_synthesis(response)
        except Exception as e:
            logger.warning(f"[Synthesizer] LLM 합성 실패, fallback: {e}")
            return None

    @staticmethod
    def _parse_synthesis(response: str) -> SynthesisResult:
        """LLM 합성 응답 파싱."""
        judgment = SynthesisJudgment.NEEDS_INTEGRATION
        reasoning = ""
        summary = ""
        follow_ups: list[dict] = []
        report_lines: list[str] = []
        in_report = False

        for line in response.strip().split("\n"):
            stripped = line.strip()
            upper = stripped.upper()

            if upper == "END_REPORT":
                in_report = False
                continue

            if in_report:
                report_lines.append(stripped)
                continue

            if upper.startswith("REPORT:"):
                in_report = True
                rest = stripped.split(":", 1)[1].strip()
                if rest:
                    report_lines.append(rest)
                continue

            if upper.startswith("JUDGMENT:"):
                val = stripped.split(":", 1)[1].strip().lower()
                # exact match first to avoid "sufficient" matching "insufficient"
                for j in SynthesisJudgment:
                    if j.value == val:
                        judgment = j
                        break
                else:
                    # partial match fallback
                    for j in sorted(SynthesisJudgment, key=lambda x: -len(x.value)):
                        if j.value in val:
                            judgment = j
                            break
            elif upper.startswith("REASONING:"):
                reasoning = stripped.split(":", 1)[1].strip()
            elif upper.startswith("SUMMARY:"):
                summary = stripped.split(":", 1)[1].strip()
            elif upper.startswith("FOLLOW_UP:"):
                rest = stripped.split(":", 1)[1].strip()
                if rest.lower() != "none":
                    _parse_follow_up_line(rest, follow_ups)
            elif "DEPT:" in upper and "TASK:" in upper:
                # follow-up 태스크 추가 라인
                _parse_follow_up_line(stripped, follow_ups)

        unified_report = "\n".join(report_lines).strip()

        return SynthesisResult(
            judgment=judgment,
            summary=summary,
            follow_up_tasks=follow_ups,
            unified_report=unified_report,
            reasoning=reasoning,
        )

    @staticmethod
    def _keyword_synthesize(subtasks: list[dict]) -> SynthesisResult:
        """키워드 기반 합성 (LLM fallback).

        - 모든 결과 존재 → sufficient
        - 결과 없는 부서 있음 → insufficient
        - 그 외 → needs_integration
        """
        lines: list[str] = []
        missing: list[str] = []

        for st in subtasks:
            dept_name = KNOWN_DEPTS.get(
                st.get("assigned_dept", ""), st.get("assigned_dept", "?"),
            )
            result = st.get("result", "")
            if not result or result == "(결과 없음)":
                missing.append(dept_name)
                lines.append(f"**{dept_name}**: (결과 없음)")
            else:
                lines.append(f"**{dept_name}**: {result[:200]}")

        unified = "\n".join(lines)

        if missing:
            return SynthesisResult(
                judgment=SynthesisJudgment.INSUFFICIENT,
                summary=f"{len(missing)}개 부서 결과 누락: {', '.join(missing)}",
                unified_report=unified,
                reasoning=f"다음 부서에서 결과를 받지 못함: {', '.join(missing)}",
                follow_up_tasks=[],
            )

        return SynthesisResult(
            judgment=SynthesisJudgment.SUFFICIENT,
            summary=f"모든 {len(subtasks)}개 부서 결과 수신 완료",
            unified_report=unified,
            reasoning="모든 부서가 결과를 제출함",
        )


def _parse_follow_up_line(line: str, follow_ups: list[dict]) -> None:
    """DEPT:xxx|TASK:yyy 형식의 follow-up 라인 파싱."""
    parts: dict[str, str] = {}
    for segment in line.split("|"):
        if ":" in segment:
            key, val = segment.split(":", 1)
            parts[key.strip().upper()] = val.strip()

    dept = parts.get("DEPT", "")
    task = parts.get("TASK", "")
    if dept and dept in KNOWN_DEPTS and task:
        follow_ups.append({"dept": dept, "description": task})
