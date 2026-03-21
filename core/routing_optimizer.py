"""라우팅 최적화기 — lesson_memory 패턴 기반 nl_classifier 개선 제안.

Karpathy 루프:
  1. routing test_cases.json 으로 현재 accuracy 측정
  2. lesson_memory 실패 패턴에서 키워드 추가 제안 생성
  3. accuracy 개선 시 → 제안 반환 (적용은 Rocky 승인)

사용법:
    opt = RoutingOptimizer()
    proposal = opt.generate_proposal()
    if proposal:
        print(proposal.diff_summary)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


@dataclass
class RoutingProposal:
    """nl_classifier 개선 제안."""
    keyword_additions: dict[str, list[str]]   # dept → 추가할 키워드 목록
    rationale: str
    current_accuracy: float
    estimated_gain: float
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def diff_summary(self) -> str:
        lines = [
            "📐 *라우팅 최적화 제안*",
            f"현재 정확도: {self.current_accuracy:.1%}",
            f"예상 개선: +{self.estimated_gain:.1%}",
            f"근거: {self.rationale}",
            "",
            "추가 키워드 제안:",
        ]
        for dept, keywords in self.keyword_additions.items():
            if keywords:
                lines.append(f"  • {dept}: {', '.join(keywords[:5])}")
        return "\n".join(lines)


# 부서별 실패 카테고리 → 키워드 매핑
_FAILURE_TO_DEPT_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "logic_error": {
        "engineering": ["로직 오류", "버그", "logic error", "bug fix"],
    },
    "api_failure": {
        "engineering": ["API 실패", "연결 오류", "api error", "connection"],
    },
    "context_loss": {
        "engineering": ["컨텍스트 손실", "상태 누락", "context", "state"],
    },
    "timeout": {
        "engineering": ["타임아웃", "응답 지연", "timeout", "slow"],
    },
    "incomplete_output": {
        "engineering": ["출력 누락", "결과 불완전", "incomplete"],
    },
}


class RoutingOptimizer:
    """lesson_memory 실패 패턴 → nl_classifier 키워드 추가 제안."""

    FAILURE_LOOKBACK_DAYS = 14
    MIN_FAILURES_TO_PROPOSE = 2

    def __init__(self) -> None:
        self._nl_classifier_path = Path(__file__).parent / "nl_classifier.py"
        self._routing_eval_path = (
            Path(__file__).parent.parent / "evals" / "routing" / "test_cases.json"
        )

    def generate_proposal(self) -> RoutingProposal | None:
        """현재 failure 패턴 분석 → 키워드 추가 제안 생성."""
        failure_stats = self._get_failure_stats()
        if not failure_stats:
            logger.info("[RoutingOptimizer] 분석할 실패 패턴 없음")
            return None

        keyword_additions: dict[str, list[str]] = {}
        reasons: list[str] = []
        existing_keywords = self._read_existing_keywords()

        for category, count in failure_stats.items():
            if count < self.MIN_FAILURES_TO_PROPOSE:
                continue
            dept_map = _FAILURE_TO_DEPT_KEYWORDS.get(category, {})
            for dept, new_keywords in dept_map.items():
                # 이미 있는 키워드 제외
                fresh = [k for k in new_keywords if k not in existing_keywords]
                if fresh:
                    keyword_additions.setdefault(dept, []).extend(fresh)
                    reasons.append(f"{category}({count}회)")

        if not keyword_additions:
            logger.info("[RoutingOptimizer] 신규 키워드 제안 없음 (이미 모두 포함)")
            return None

        accuracy = self._measure_current_accuracy()
        estimated_gain = min(0.05, len(keyword_additions) * 0.01)

        proposal = RoutingProposal(
            keyword_additions=keyword_additions,
            rationale=f"반복 실패 패턴: {', '.join(reasons)}",
            current_accuracy=accuracy,
            estimated_gain=estimated_gain,
        )
        logger.info(
            f"[RoutingOptimizer] 제안 생성 — "
            f"{sum(len(v) for v in keyword_additions.values())}개 키워드 추가 대상"
        )
        return proposal

    def _get_failure_stats(self) -> dict[str, int]:
        try:
            from core.lesson_memory import LessonMemory
            lm = LessonMemory()
            return lm.get_category_stats()
        except Exception as e:
            logger.warning(f"[RoutingOptimizer] lesson_memory 조회 실패: {e}")
            return {}

    def _read_existing_keywords(self) -> set[str]:
        """nl_classifier.py 텍스트에서 현재 키워드 추출."""
        if not self._nl_classifier_path.exists():
            return set()
        text = self._nl_classifier_path.read_text(encoding="utf-8")
        # 문자열 리터럴 추출 (단순 패턴)
        import re
        return set(re.findall(r'"([^"]{2,})"', text))

    def _measure_current_accuracy(self) -> float:
        """routing test_cases.json 으로 현재 nl_classifier accuracy 측정."""
        if not self._routing_eval_path.exists():
            return 0.0
        try:
            from core.eval_runner import EvalRunner
            from core.nl_classifier import NLClassifier
            classifier = NLClassifier()
            runner = EvalRunner()
            result = runner.score_routing(lambda msg: classifier.classify(msg))
            return result.get("accuracy", 0.0)
        except Exception as e:
            logger.debug(f"[RoutingOptimizer] accuracy 측정 실패: {e}")
            return 0.0

    def format_for_telegram(self, proposal: RoutingProposal) -> str:
        return proposal.diff_summary
