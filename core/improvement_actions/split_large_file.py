"""split_large_file 액션 — 크리티컬 크기 파일에 대해
SelfCodeImprover를 통해 모듈 분리를 요청한다.

dry_run=True이면 실제 수정 없이 계획만 반환한다.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.improvement_actions.base import ActionResult, BaseAction
from core.health_report_parser import ImprovementItem

REPO_ROOT = Path(__file__).parent.parent.parent


class SplitLargeFileAction(BaseAction):
    """대형 파일 → SelfCodeImprover를 통해 모듈 분리 시도."""

    name = "split_large_file"

    def run(self, item: ImprovementItem) -> ActionResult:
        file_path = item.file_path or "unknown"
        size_kb = item.detail.get("size_kb", 0)
        target = file_path

        logger.info(f"[SplitLargeFileAction] 분리 시도: {file_path} ({size_kb:.0f}KB)")

        if self.dry_run:
            msg = (
                f"[dry_run] {file_path} ({size_kb:.0f}KB) — "
                "모듈 분리 계획 생성 완료 (실제 실행 안 함)"
            )
            logger.info(f"[SplitLargeFileAction] {msg}")
            return ActionResult(
                action_name=self.name,
                target=target,
                success=True,
                dry_run=True,
                message=msg,
            )

        # rate limit 확인 (SelfCodeImprover 내부에서도 하지만 여기서도 선 체크)
        from core.self_code_improver import SelfCodeImprover
        improver = SelfCodeImprover(dry_run=False)

        # 실제 파일 존재 여부 확인
        abs_path = REPO_ROOT / file_path
        if not abs_path.exists():
            msg = f"{file_path} 파일을 찾을 수 없음 — 스킵"
            logger.warning(f"[SplitLargeFileAction] {msg}")
            return ActionResult(
                action_name=self.name, target=target, success=False, message=msg
            )

        fix_result = improver.fix(
            target=file_path,
            error_summary=(
                f"{file_path} 파일이 {size_kb:.0f}KB로 임계값 초과. "
                "논리적으로 분리 가능한 기능을 별도 모듈로 추출하라. "
                "public API는 backward-compatible하게 유지할 것."
            ),
            related_files=[file_path],
        )

        if fix_result and fix_result.success:
            msg = f"분리 완료 — branch={fix_result.branch}, commit={fix_result.commit_hash[:7]}"
            logger.info(f"[SplitLargeFileAction] {msg}")
            return ActionResult(
                action_name=self.name, target=target, success=True, message=msg
            )

        attempts = fix_result.attempts if fix_result else 0
        msg = f"자동 분리 실패 ({attempts}회 시도) — 수동 검토 필요"
        logger.error(f"[SplitLargeFileAction] {msg}")
        return ActionResult(
            action_name=self.name, target=target, success=False, message=msg
        )
