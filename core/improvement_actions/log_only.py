"""log_only 액션 — warn 수준 항목을 로그에만 기록하고 실제 수정은 하지 않는다."""
from __future__ import annotations

from loguru import logger

from core.improvement_actions.base import ActionResult, BaseAction
from core.health_report_parser import ImprovementItem


class LogOnlyAction(BaseAction):
    """개선 항목을 로그에만 기록한다. warn 수준 파일 크기 등에 사용."""

    name = "log_only"

    def run(self, item: ImprovementItem) -> ActionResult:
        target = item.file_path or item.error_pattern or "unknown"
        logger.info(
            f"[LogOnlyAction] 기록됨 — {target}: {item.suggested_action}"
        )
        return ActionResult(
            action_name=self.name,
            target=target,
            success=True,
            dry_run=self.dry_run,
            message=f"로그 기록 완료: {item.suggested_action}",
        )
