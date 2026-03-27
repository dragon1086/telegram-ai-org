"""PM Judgment Gate — COLLAB 결과 품질 평가 및 재진입 판단."""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from core.pm_decision import DecisionClientProtocol


class JudgmentVerdict(str, Enum):
    APPROVE = "approve"      # 결과 충분 → 합성 진행
    REROUTE = "reroute"      # 다른 부서로 재라우팅 필요
    REJECT  = "reject"       # 결과 불충분 → 동일 부서 재작업


@dataclass
class JudgmentResult:
    verdict: JudgmentVerdict
    reasoning: str
    suggested_dept: str = ""      # REROUTE 시 대상 부서 org_id
    rework_prompt: str = ""       # REJECT 시 보완 지시


class PMJudgmentGate:
    """COLLAB 결과를 평가해 PM 판단(승인/재라우팅/거부)을 내린다."""

    # 결과가 비어 있거나 너무 짧으면 자동 REJECT
    MIN_RESULT_LENGTH = 20

    def evaluate_sync(
        self,
        task_description: str,
        result: str,
        context: str = "",
    ) -> JudgmentResult:
        """동기 휴리스틱 평가. LLM 없이 즉각 판단."""
        stripped = (result or "").strip()
        if len(stripped) < self.MIN_RESULT_LENGTH:
            return JudgmentResult(
                verdict=JudgmentVerdict.REJECT,
                reasoning=f"결과가 너무 짧습니다 ({len(stripped)}자 < {self.MIN_RESULT_LENGTH}자 기준).",
                rework_prompt="더 구체적이고 완전한 결과를 제공해 주세요.",
            )

        # 오류 패턴 감지
        error_markers = ["traceback", "error:", "exception:", "실패", "오류 발생"]
        lower = stripped.lower()
        if any(m in lower for m in error_markers) and len(stripped) < 200:
            return JudgmentResult(
                verdict=JudgmentVerdict.REJECT,
                reasoning="결과에 오류 패턴이 감지됩니다.",
                rework_prompt="오류를 수정하고 정상 결과를 반환해 주세요.",
            )

        return JudgmentResult(
            verdict=JudgmentVerdict.APPROVE,
            reasoning="결과가 충분합니다.",
        )

    async def evaluate(
        self,
        task_description: str,
        result: str,
        context: str = "",
        decision_client: Optional["DecisionClientProtocol"] = None,
    ) -> JudgmentResult:
        """비동기 LLM 기반 평가. 실패 시 휴리스틱으로 폴백."""
        # 먼저 동기 휴리스틱으로 명백한 케이스 처리
        quick = self.evaluate_sync(task_description, result, context)
        if quick.verdict != JudgmentVerdict.APPROVE:
            return quick

        if decision_client is None:
            return quick

        try:
            prompt = (
                "다음 COLLAB 태스크 결과를 평가하라.\n\n"
                f"태스크: {task_description[:300]}\n"
                f"컨텍스트: {context[:200]}\n"
                f"결과:\n{result[:800]}\n\n"
                "판단 기준:\n"
                "- approve: 태스크를 충분히 수행함\n"
                "- reroute: 다른 전문 부서가 처리해야 함 (suggested_dept 명시)\n"
                "- reject: 결과가 태스크 요구사항을 충족하지 못함\n\n"
                "JSON으로 응답: {\"verdict\":\"approve|reroute|reject\","
                "\"reasoning\":\"한 문장\","
                "\"suggested_dept\":\"org_id or empty\","
                "\"rework_prompt\":\"보완 지시 or empty\"}"
            )
            raw = await decision_client.ask(prompt)
            import json, re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                verdict_str = data.get("verdict", "approve")
                try:
                    verdict = JudgmentVerdict(verdict_str)
                except ValueError:
                    verdict = JudgmentVerdict.APPROVE
                return JudgmentResult(
                    verdict=verdict,
                    reasoning=data.get("reasoning", ""),
                    suggested_dept=data.get("suggested_dept", ""),
                    rework_prompt=data.get("rework_prompt", ""),
                )
        except Exception as e:
            logger.warning(f"[PMJudgmentGate] LLM 평가 실패, 휴리스틱 폴백: {e}")

        return quick
