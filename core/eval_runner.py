"""스킬 Eval 실행기 — eval.json 기반 스킬 품질 점수 측정.

evals/skills/{skill-name}/eval.json 을 읽어 시나리오별 점수를 측정한다.
Karpathy 루프의 측정 레이어: score_before → change → score_after → keep/revert

사용법:
    runner = EvalRunner()
    result = runner.score_skill("pm-task-dispatch")
    print(result.score)          # 0.0 ~ 10.0
    print(result.passed)         # bool
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

EVALS_DIR = Path(__file__).parent.parent / "evals"
SKILL_EVALS_DIR = EVALS_DIR / "skills"
ROUTING_EVALS_DIR = EVALS_DIR / "routing"

PASS_THRESHOLD = 7.0        # 이 점수 이상이면 PASS


@dataclass
class EvalScenario:
    id: str
    input: str
    expected: str           # 기대 동작 또는 정답 봇
    weight: float = 1.0
    tags: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    skill_name: str
    score: float            # 0.0 ~ 10.0
    baseline: float
    passed: bool
    improved: bool          # score > baseline
    scenario_count: int
    details: list[dict]
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def delta(self) -> float:
        return round(self.score - self.baseline, 2)


class EvalRunner:
    """eval.json 기반 스킬 품질 평가."""

    def __init__(self) -> None:
        self._skill_dir = SKILL_EVALS_DIR
        self._routing_dir = ROUTING_EVALS_DIR

    # ------------------------------------------------------------------
    # 스킬 평가
    # ------------------------------------------------------------------

    def score_skill(self, skill_name: str) -> EvalResult | None:
        """단일 스킬 평가. eval.json 없으면 None."""
        eval_path = self._skill_dir / skill_name / "eval.json"
        if not eval_path.exists():
            logger.debug(f"[EvalRunner] eval.json 없음: {skill_name}")
            return None

        data = json.loads(eval_path.read_text(encoding="utf-8"))
        baseline = float(data.get("baseline", 5.0))
        scenarios = [
            EvalScenario(
                id=s.get("id", f"s{i}"),
                input=s["input"],
                expected=s.get("expected", ""),
                weight=float(s.get("weight", 1.0)),
                tags=s.get("tags", []),
            )
            for i, s in enumerate(data.get("scenarios", []))
        ]

        if not scenarios:
            logger.warning(f"[EvalRunner] 시나리오 없음: {skill_name}")
            return None

        skill_path = self._find_skill_path(skill_name)
        if skill_path is None:
            logger.warning(f"[EvalRunner] 스킬 파일 없음: {skill_name}")
            return None

        skill_text = skill_path.read_text(encoding="utf-8")
        details, total_score = self._run_scenarios(scenarios, skill_text, data)

        score = round(total_score, 2)
        result = EvalResult(
            skill_name=skill_name,
            score=score,
            baseline=baseline,
            passed=score >= PASS_THRESHOLD,
            improved=score > baseline,
            scenario_count=len(scenarios),
            details=details,
        )
        logger.info(
            f"[EvalRunner] {skill_name}: {score:.1f}/10 "
            f"(baseline={baseline}, delta={result.delta:+.1f})"
        )
        return result

    def score_all_skills(self) -> list[EvalResult]:
        """evals/skills/ 아래 모든 스킬 평가."""
        results = []
        if not self._skill_dir.exists():
            return results
        for eval_json in sorted(self._skill_dir.glob("*/eval.json")):
            skill_name = eval_json.parent.name
            result = self.score_skill(skill_name)
            if result:
                results.append(result)
        return results

    # ------------------------------------------------------------------
    # 라우팅 정확도 평가
    # ------------------------------------------------------------------

    def score_routing(self, classifier_fn) -> dict:
        """routing/test_cases.json 기반 라우팅 정확도 측정.

        Args:
            classifier_fn: (message: str) -> str 형태의 분류 함수
        Returns:
            {"accuracy": float, "correct": int, "total": int, "errors": list}
        """
        test_path = self._routing_dir / "test_cases.json"
        if not test_path.exists():
            return {"accuracy": 0.0, "correct": 0, "total": 0, "errors": []}

        data = json.loads(test_path.read_text(encoding="utf-8"))
        cases = data.get("test_cases", [])
        baseline = data.get("baseline_accuracy", 0.0)

        correct = 0
        errors = []
        for case in cases:
            msg = case["input"]
            expected = case["correct_bot"]
            try:
                predicted = classifier_fn(msg)
                if predicted == expected:
                    correct += 1
                else:
                    errors.append({
                        "id": case.get("id", "?"),
                        "input": msg,
                        "expected": expected,
                        "predicted": predicted,
                    })
            except Exception as e:
                errors.append({"id": case.get("id", "?"), "error": str(e)})

        total = len(cases)
        accuracy = correct / total if total > 0 else 0.0
        return {
            "accuracy": round(accuracy, 4),
            "correct": correct,
            "total": total,
            "baseline": baseline,
            "improved": accuracy > baseline,
            "errors": errors[:10],  # 처음 10개만
        }

    # ------------------------------------------------------------------
    # 내부 평가 로직
    # ------------------------------------------------------------------

    def _run_scenarios(
        self,
        scenarios: list[EvalScenario],
        skill_text: str,
        eval_data: dict,
    ) -> tuple[list[dict], float]:
        """시나리오별 점수 계산. 가중 평균 반환."""
        metrics = eval_data.get("metrics", {})
        details = []
        weighted_sum = 0.0
        weight_total = 0.0

        for scenario in scenarios:
            scenario_score = self._score_scenario(scenario, skill_text, metrics)
            details.append({
                "id": scenario.id,
                "score": scenario_score,
                "weight": scenario.weight,
            })
            weighted_sum += scenario_score * scenario.weight
            weight_total += scenario.weight

        total_score = (weighted_sum / weight_total * 10.0) if weight_total > 0 else 0.0
        return details, total_score

    def _score_scenario(
        self,
        scenario: EvalScenario,
        skill_text: str,
        metrics: dict,
    ) -> float:
        """단일 시나리오 점수 (0.0 ~ 1.0).

        평가 기준:
        - expected 키워드가 skill_text에 포함되는지
        - 명확성 지표 (문장 구조, 트리거 패턴 존재)
        """
        score = 0.0

        # 1. expected 키워드 커버리지
        expected_words = [w.lower() for w in scenario.expected.split() if len(w) > 2]
        if expected_words:
            skill_lower = skill_text.lower()
            matched = sum(1 for w in expected_words if w in skill_lower)
            score += 0.6 * (matched / len(expected_words))

        # 2. 입력 시나리오가 트리거 섹션에 언급되는지
        input_words = [w.lower() for w in scenario.input.split() if len(w) > 2]
        if input_words:
            skill_lower = skill_text.lower()
            trigger_section = self._extract_section(skill_text, "trigger")
            search_text = trigger_section if trigger_section else skill_lower
            matched_input = sum(1 for w in input_words if w in search_text)
            score += 0.4 * min(1.0, matched_input / max(1, len(input_words) // 2))

        return min(1.0, score)

    def _extract_section(self, text: str, section_name: str) -> str:
        """마크다운 섹션 추출."""
        pattern = rf"#{1,3}\s*{re.escape(section_name)}.*?\n(.*?)(?=#{1,3}\s|\Z)"
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return m.group(1) if m else ""

    def _find_skill_path(self, skill_name: str) -> Path | None:
        """skills/ 또는 .claude/skills/ 에서 SKILL.md 탐색."""
        project_root = Path(__file__).parent.parent
        candidates = [
            project_root / "skills" / skill_name / "SKILL.md",
            project_root / ".claude" / "skills" / skill_name / "SKILL.md",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    # ------------------------------------------------------------------
    # 보고서 포맷
    # ------------------------------------------------------------------

    def format_results(self, results: list[EvalResult]) -> str:
        if not results:
            return "eval.json이 있는 스킬 없음."
        lines = ["📊 *스킬 Eval 결과*", ""]
        for r in sorted(results, key=lambda x: x.score, reverse=True):
            icon = "✅" if r.passed else "⚠️"
            trend = f"({r.delta:+.1f})" if r.delta != 0 else ""
            lines.append(
                f"{icon} *{r.skill_name}*: {r.score:.1f}/10 {trend}"
            )
        passing = sum(1 for r in results if r.passed)
        lines.append(f"\n합계: {passing}/{len(results)} PASS")
        return "\n".join(lines)
