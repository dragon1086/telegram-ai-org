"""fix_error_pattern 액션 — 반복 에러 패턴에 대해
SelfCodeImprover를 통해 자동 수정을 시도한다.

패턴 이름으로 관련 파일을 추론하고 개선 프롬프트를 구성한다.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.health_report_parser import ImprovementItem
from core.improvement_actions.base import ActionResult, BaseAction

REPO_ROOT = Path(__file__).parent.parent.parent

# 알려진 에러 패턴 → 주로 수정이 필요한 파일 힌트
_PATTERN_FILE_HINTS: dict[str, list[str]] = {
    "approach":         ["core/pm_orchestrator.py", "core/dispatch_engine.py"],
    "timeout":          ["core/task_poller.py", "core/completion.py"],
    "routing":          ["core/pm_router.py", "core/routing_keywords.py"],
    "context_loss":     ["core/context_db.py", "core/shared_memory.py"],
    "logic_error":      ["core/pm_orchestrator.py"],
    "import":           ["core/pm_orchestrator.py"],
}


class FixErrorPatternAction(BaseAction):
    """반복 에러 패턴 → SelfCodeImprover 자동 수정."""

    name = "fix_error_pattern"

    def run(self, item: ImprovementItem) -> ActionResult:
        pattern = item.error_pattern or "unknown_pattern"
        count = item.detail.get("count", 0)
        target = f"error_pattern:{pattern}"

        logger.info(f"[FixErrorPatternAction] 패턴 수정 시도: {pattern} ({count}회)")

        if self.dry_run:
            msg = f"[dry_run] '{pattern}' 패턴 수정 계획 (실제 실행 안 함)"
            return ActionResult(
                action_name=self.name, target=target, success=True,
                dry_run=True, message=msg,
            )

        related_files = self._resolve_related_files(pattern)
        if not related_files:
            msg = f"'{pattern}' 패턴에 관련 파일을 특정할 수 없어 스킵"
            logger.warning(f"[FixErrorPatternAction] {msg}")
            return ActionResult(
                action_name=self.name, target=target, success=False, message=msg
            )

        from core.self_code_improver import SelfCodeImprover
        improver = SelfCodeImprover(dry_run=False)
        fix_result = improver.fix(
            target=related_files[0],
            error_summary=(
                f"'{pattern}' 에러 패턴이 최근 {count}회 반복됨. "
                "근본 원인을 파악하고 재발을 막는 방어 코드를 추가하라. "
                "실패 재현 테스트를 먼저 작성할 것(TDD)."
            ),
            related_files=related_files,
        )

        if fix_result and fix_result.success:
            msg = f"'{pattern}' 수정 완료 — branch={fix_result.branch}"
            logger.info(f"[FixErrorPatternAction] {msg}")
            return ActionResult(
                action_name=self.name, target=target, success=True, message=msg
            )

        attempts = fix_result.attempts if fix_result else 0
        msg = f"'{pattern}' 자동 수정 실패 ({attempts}회 시도)"
        logger.error(f"[FixErrorPatternAction] {msg}")
        return ActionResult(
            action_name=self.name, target=target, success=False, message=msg
        )

    def _resolve_related_files(self, pattern: str) -> list[str]:
        """패턴 이름으로 관련 파일 목록 반환. 실제 존재하는 파일만."""
        hints = _PATTERN_FILE_HINTS.get(pattern.lower(), [])
        existing = [f for f in hints if (REPO_ROOT / f).exists()]
        if existing:
            return existing
        # 힌트 없으면 core/ 에서 패턴명 포함 파일 검색
        guesses = list(REPO_ROOT.glob(f"core/*{pattern.lower()}*.py"))
        return [str(g.relative_to(REPO_ROOT)) for g in guesses[:3]]
