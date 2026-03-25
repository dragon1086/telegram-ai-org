"""스킬 자동 개선 — autoresearch 루프 (N variants -> EvalRunner -> keep best)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

SKILLS_DIR = Path(__file__).parent.parent / "skills"
EVALS_DIR = Path(__file__).parent.parent / "evals" / "skills"
MAX_VARIANTS = 3
MIN_IMPROVEMENT = 0.5  # baseline 대비 최소 개선폭


@dataclass
class ImprovementResult:
    skill_name: str
    original_score: float
    best_score: float
    variant_applied: str
    improved: bool


class SkillAutoImprover:
    """스킬 SKILL.md를 N개 변형 -> eval -> 최고 점수 keep/revert."""

    def improve(self, skill_name: str) -> ImprovementResult | None:
        from core.eval_runner import EvalRunner
        runner = EvalRunner()
        baseline_result = runner.score_skill(skill_name)
        if baseline_result is None:
            logger.info(f"[SkillAutoImprover] {skill_name}: eval.json 없음, 스킵")
            return None

        skill_path = SKILLS_DIR / skill_name / "SKILL.md"
        if not skill_path.exists():
            logger.warning(f"[SkillAutoImprover] {skill_name}: SKILL.md 없음")
            return None

        original_content = skill_path.read_text(encoding="utf-8")
        original_score = baseline_result.score

        failure_summary = self._get_failure_summary(skill_name)
        variants = self._generate_variants(original_content, failure_summary)

        best_score = original_score
        best_variant = original_content

        for i, variant in enumerate(variants):
            skill_path.write_text(variant, encoding="utf-8")
            score = self._score_variant(skill_name)
            logger.info(f"[SkillAutoImprover] {skill_name} variant {i + 1}: {score:.1f}")
            if score > best_score:
                best_score = score
                best_variant = variant

        if best_score >= original_score + MIN_IMPROVEMENT:
            skill_path.write_text(best_variant, encoding="utf-8")
            logger.info(
                f"[SkillAutoImprover] {skill_name} 개선 적용: "
                f"{original_score:.1f} -> {best_score:.1f}"
            )
            return ImprovementResult(
                skill_name=skill_name,
                original_score=original_score,
                best_score=best_score,
                variant_applied=best_variant[:200],
                improved=True,
            )
        else:
            skill_path.write_text(original_content, encoding="utf-8")
            logger.info(f"[SkillAutoImprover] {skill_name} 개선 없음, 원본 복원")
            return ImprovementResult(
                skill_name=skill_name,
                original_score=original_score,
                best_score=best_score,
                variant_applied="",
                improved=False,
            )

    def _score_variant(self, skill_name: str) -> float:
        from core.eval_runner import EvalRunner
        result = EvalRunner().score_skill(skill_name)
        return result.score if result else 0.0

    def _get_failure_summary(self, skill_name: str) -> str:
        try:
            from core.lesson_memory import LessonMemory
            failures = LessonMemory().get_recent_failures(days=14)
            return f"최근 {len(failures)}개 실패 케이스"
        except Exception:
            return "실패 데이터 없음"

    def _generate_variants(self, content: str, failure_summary: str) -> list[str]:
        """N개 변형 생성. Claude CLI 없으면 규칙 기반 fallback."""
        variants: list[str] = []
        # Variant A: 실패 시나리오 명시 추가
        variants.append(
            content + f"\n\n## 주의 사항\n{failure_summary}에서 도출된 엣지 케이스를 반드시 처리할 것."
        )
        # Variant B: 판단 기준 수치화 힌트
        variants.append(
            content.replace("판단", "수치 기반 판단 (점수 7.0 이상 기준)", 1)
            if "판단" in content
            else content + "\n\n> 판단 기준: 점수 7.0 이상."
        )
        # Variant C: Claude CLI 기반 (가능 시)
        claude_variant = self._generate_via_claude(content, failure_summary)
        if claude_variant:
            variants.append(claude_variant)
        return variants[:MAX_VARIANTS]

    def _generate_via_claude(self, content: str, failure_summary: str) -> str | None:
        """claude --print으로 개선 변형 생성."""
        prompt = (
            f"다음 스킬 문서를 개선하라. {failure_summary}를 고려하여 "
            f"구체성과 명확성을 높여라. 원본 구조는 유지.\n\n---\n{content[:2000]}"
        )
        try:
            result = subprocess.run(
                ["claude", "--print", "-p", prompt],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None
