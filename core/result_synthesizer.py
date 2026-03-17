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
    artifact_paths: list[str] = field(default_factory=list)  # LLM이 선별한 첨부 파일 경로


_SYNTHESIS_PROMPT = (
    "You are a PM synthesizing results from multiple departments.\n\n"
    "ORIGINAL REQUEST: {original_request}\n\n"
    "DEPARTMENT RESULTS:\n{dept_results}\n\n"
    "Analyze the results and respond in this EXACT format:\n"
    "JUDGMENT: sufficient | insufficient | conflicting | needs_integration\n"
    "REASONING: one-line explanation of your judgment\n"
    "SUMMARY: unified summary of all results (2-3 sentences)\n"
    "FOLLOW_UP: DEPT:aiorg_xxx_bot|TASK:description (one per line, or 'none')\n"
    "ARTIFACTS: /absolute/path/to/file.png (one per line, or 'none')\n"
    "REPORT:\n"
    "final integrated report for the user\n"
    "END_REPORT\n\n"
    "Rules:\n"
    "- SUFFICIENT: all departments delivered what was needed\n"
    "- INSUFFICIENT: key deliverables missing or incomplete\n"
    "- CONFLICTING: departments contradict each other\n"
    "- NEEDS_INTEGRATION: results are good but need to be combined into one coherent output\n"
    "- Write in Korean\n"
    "- The REPORT must be user-facing, answer-first, and helpful.\n"
    "- First paragraph: directly answer what the user cares about.\n"
    "- Then include ALL key findings from every department — do NOT summarize away details.\n"
    "- Organize findings by department or topic for clarity.\n"
    "- Do NOT reply with only file paths, links, or location hints.\n"
    "- If artifacts/files exist, mention them only as supplements after explaining the substance.\n"
    "- ARTIFACTS: list only files that are genuinely useful to the user (images, reports, docs).\n"
    "  Exclude temp files, logs, lock files. Write absolute paths as they appear in results.\n"
    "  If no files worth sending, write ARTIFACTS: none\n"
    "- FOLLOW_UP: Only add when the user's original request is genuinely NOT yet fulfilled.\n"
    "  DO NOT create follow-ups just because departments mentioned future plans or next steps.\n"
    "  If judgment is SUFFICIENT, write FOLLOW_UP: none in almost all cases.\n"
    "  Only exception: user explicitly asked for a multi-step deliverable and a step is missing.\n"
)


_DEBATE_SYNTHESIS_PROMPT = (
    "당신은 AI 조직의 PM입니다. 여러 부서가 동일한 주제에 대해 각자의 관점에서 의견을 제시했습니다.\n\n"
    "주제: {topic}\n\n"
    "각 부서의 의견:\n{opinions}\n\n"
    "다음 형식으로 종합 결론을 작성하세요:\n"
    "1. 각 부서 입장 한 줄 요약\n"
    "2. 공통점 (있다면)\n"
    "3. 핵심 차이점/갈등 지점\n"
    "4. PM 종합 판단 및 권고안\n\n"
    "간결하고 실용적으로 작성하세요."
)


class ResultSynthesizer:
    """부서 결과를 LLM으로 분석·판단하는 합성기."""

    def __init__(self, decision_client: DecisionClientProtocol | None = None) -> None:
        self._decision_client = decision_client

    async def synthesize_debate(self, topic: str, opinions: list[dict]) -> str:
        """debate 모드 전용 synthesis — 관점 비교 + 결론."""
        if self._decision_client is None:
            return self._keyword_debate(opinions)

        opinions_text = "\n".join(
            f"[{op.get('dept_name', op.get('bot_id', '?'))}] {op.get('content', '(응답 없음)')}"
            for op in opinions
        )
        prompt = _DEBATE_SYNTHESIS_PROMPT.format(
            topic=topic[:500],
            opinions=opinions_text[:4000],
        )
        try:
            return await asyncio.wait_for(
                self._decision_client.complete(prompt),
                timeout=180.0,
            )
        except Exception as e:
            logger.warning(f"[Synthesizer] debate LLM 합성 실패, fallback: {e}")
            return self._keyword_debate(opinions)

    @staticmethod
    def _keyword_debate(opinions: list[dict]) -> str:
        """LLM 없을 때 단순 나열 fallback."""
        lines = [
            f"- {op.get('dept_name', op.get('bot_id', '?'))}: {op.get('content', '(응답 없음)')[:120]}"
            for op in opinions
        ]
        return "각 부서 의견:\n" + "\n".join(lines)

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
        if self._decision_client is None:
            return None

        dept_results = "\n".join(
            f"## [{KNOWN_DEPTS.get(st.get('assigned_dept', ''), st.get('assigned_dept', '?'))}]\n"
            f"{_result_excerpt(st.get('result', '(결과 없음)'))}"
            for st in subtasks
        )

        prompt = _SYNTHESIS_PROMPT.format(
            original_request=original_request[:2000],
            dept_results=dept_results,
        )

        try:
            response = await asyncio.wait_for(
                self._decision_client.complete(prompt),
                timeout=180.0,
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
        artifact_paths: list[str] = []
        report_lines: list[str] = []
        in_report = False
        in_artifacts = False

        for line in response.strip().split("\n"):
            stripped = line.strip()
            upper = stripped.upper()

            if upper == "END_REPORT":
                in_report = False
                continue

            if in_report:
                in_artifacts = False
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
            elif upper.startswith("ARTIFACTS:"):
                in_artifacts = True
                rest = stripped.split(":", 1)[1].strip()
                if rest.lower() != "none" and rest:
                    artifact_paths.append(rest)
            elif in_artifacts and (stripped.startswith("/") or stripped.startswith("~")):
                # ARTIFACTS 섹션 이후 경로만 나열된 추가 줄
                artifact_paths.append(stripped)
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
            artifact_paths=artifact_paths,
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
                lines.append(f"**{dept_name}**\n\n{result.lstrip('-').strip()}")

        if missing:
            return SynthesisResult(
                judgment=SynthesisJudgment.INSUFFICIENT,
                summary=f"{len(missing)}개 부서 결과 누락: {', '.join(missing)}",
                unified_report=_build_fallback_public_report(lines, missing=missing),
                reasoning=f"다음 부서에서 결과를 받지 못함: {', '.join(missing)}",
                follow_up_tasks=[],
            )

        return SynthesisResult(
            judgment=SynthesisJudgment.SUFFICIENT,
            summary=f"모든 {len(subtasks)}개 부서 결과 수신 완료",
            unified_report=_build_fallback_public_report(lines),
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


def _result_excerpt(result: str, limit: int = 2200) -> str:
    text = (result or "(결과 없음)").strip()
    if len(text) <= limit:
        return text
    head = text[:1400].rstrip()
    tail = text[-600:].lstrip()
    return f"{head}\n\n[중간 내용 생략]\n\n{tail}"


def _build_fallback_public_report(lines: list[str], missing: list[str] | None = None) -> str:
    header = "현재까지 확인된 핵심 결과를 먼저 정리합니다."
    if missing:
        header = (
            "아직 일부 조직 결과가 빠져 있어서 최종 결론을 확정하긴 이릅니다. "
            "다만 현재까지 확인된 내용은 아래와 같습니다."
        )
    details = "\n\n".join(line for line in lines)
    if missing:
        details += f"\n- 추가 확인 필요: {', '.join(missing)}"
    return f"{header}\n\n{details}".strip()
